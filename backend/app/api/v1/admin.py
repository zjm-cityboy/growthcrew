"""管理后台路由：仅 GC_ADMIN_USERNAMES 中的用户可访问（部署者管理全部用户数据）。"""

import json
from datetime import date as _date
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_admin_user, get_session
from app.domain.enums import GoalStatus, SkipReason, TaskStatus
from app.models.goal import Goal, Milestone
from app.models.journal import DailyJournal, LifeLog
from app.models.mistake import Mistake
from app.models.notification import Notification
from app.models.plan import PlanProposal, Task, WeeklyPlan
from app.models.report import WeeklyReport
from app.models.user import User
from app.services.admin import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])

# 备份导出的表（有序，便于人工阅读与迁移参考）。
# 敏感字段不导出：密码哈希、加密后的模型密钥、推送端点凭据部分。
_BACKUP_TABLES: list[tuple[str, Any]] = [
    ("users", User),
    ("goals", Goal),
    ("milestones", Milestone),
    ("weekly_plans", WeeklyPlan),
    ("tasks", Task),
    ("plan_proposals", PlanProposal),
    ("daily_journals", DailyJournal),
    ("life_logs", LifeLog),
    ("weekly_reports", WeeklyReport),
    ("notifications", Notification),
    ("mistakes", Mistake),
]
_BACKUP_EXCLUDED_COLUMNS = {"password_hash", "api_key_encrypted", "endpoint"}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, _date)):
        return value.isoformat()
    return value


async def _dump_table(session: AsyncSession, model: Any) -> list[dict[str, Any]]:
    rows = (await session.execute(select(model))).scalars().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                c.name: _jsonable(getattr(row, c.name))
                for c in model.__table__.columns
                if c.name not in _BACKUP_EXCLUDED_COLUMNS
            }
        )
    return out


class SetActiveIn(BaseModel):
    active: bool


class CreateUserIn(BaseModel):
    """管理员建号：约束与用户注册一致——否则能造出登录端永远 422 的死号。"""

    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=8, max_length=128)


class GoalUpdateIn(BaseModel):
    """目标编辑：全部可选，只改传了的字段。

    status/deadline 用枚举与 date 类型——裸 str 直写枚举列曾可落脏值，
    一行脏数据会让整表读取抛 LookupError（列表 500 且无法从 UI 自救）。
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    deadline: "_date | None" = None
    weekly_hours: float | None = Field(default=None, ge=1, le=80)
    status: GoalStatus | None = None


class TaskUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    date: "_date | None" = None
    duration_minutes: int | None = Field(default=None, ge=5, le=240)
    status: TaskStatus | None = None
    skip_reason: SkipReason | None = None


class AdminRejectIn(BaseModel):
    reason: str = Field(default="", max_length=200)


class AdminUserOut(BaseModel):
    id: int
    username: str
    created_at: str
    is_active: bool
    goals: int
    active_goals: int
    tasks_total: int
    tasks_done: int
    llm_configured: bool


@router.get("/overview")
async def admin_overview(
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    _ = current_user
    ov = await AdminService(session).overview()
    return {
        "users": ov.users,
        "goals": ov.goals,
        "tasks_total": ov.tasks_total,
        "tasks_done": ov.tasks_done,
        "proposals": ov.proposals,
        "reports": ov.reports,
        "journals": ov.journals,
        "life_logs": ov.life_logs,
    }


@router.get("/users", response_model=list[AdminUserOut])
async def admin_users(
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> list[AdminUserOut]:
    _ = current_user
    rows = await AdminService(session).users()
    return [
        AdminUserOut(
            id=r.id,
            username=r.username,
            created_at=str(r.created_at)[:19],
            is_active=r.is_active,
            goals=r.goals,
            active_goals=r.active_goals,
            tasks_total=r.tasks_total,
            tasks_done=r.tasks_done,
            llm_configured=r.llm_configured,
        )
        for r in rows
    ]


@router.get("/proposals")
async def admin_proposals(
    limit: int = 30,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    _ = current_user
    return await AdminService(session).proposals(limit=limit)


@router.get("/backup")
async def admin_backup(
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """全库 JSON 备份下载（管理员数据留存用；敏感字段不导出）。"""
    _ = current_user
    payload: dict[str, Any] = {
        "exported_at": datetime.now().isoformat(),
        "note": "敏感字段（密码哈希/模型密钥/推送端点）不导出；仅作数据留存与迁移参考",
        "tables": {},
    }
    for name, model in _BACKUP_TABLES:
        payload["tables"][name] = await _dump_table(session, model)
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"growthcrew-backup-{_date.today().isoformat()}.json"
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/users/{user_id}/reset-history")
async def admin_reset_user_history(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int | str]:
    """清空指定用户的执行历史（账号/目标/密钥保留；与用户自助清空同一条路径）。"""
    _ = current_user
    from app.repositories.user import UserRepository

    target = await UserRepository(session).get(user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    removed = await AdminService(session).reset_user_history(user_id)
    return {
        "removed_tasks": removed,
        "message": f"已清空用户 {target.username} 的执行历史（目标与配置保留）",
    }


@router.patch("/users/{user_id}/active")
async def admin_set_user_active(
    user_id: int,
    payload: SetActiveIn,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str | bool]:
    """禁用/启用账号：禁用后该用户无法登录、已有令牌即刻失效。"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="不能对自己执行禁用/启用"
        )
    try:
        await AdminService(session).set_user_active(user_id, payload.active)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    target = await session.get(User, user_id)
    username = target.username if target else ""
    return {
        "username": username,
        "is_active": payload.active,
        "message": f"账号 {username} 已{'启用' if payload.active else '禁用'}",
    }


@router.post("/users/{user_id}/reset-password")
async def admin_reset_user_password(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """重置用户密码为随机临时密码（返回一次，管理员转告用户）。"""
    _ = current_user
    try:
        temp_password = await AdminService(session).reset_user_password(user_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    target = await session.get(User, user_id)
    username = target.username if target else ""
    return {
        "username": username,
        "temp_password": temp_password,
        "message": f"已重置 {username} 的密码，临时密码仅此一次可见，请立即转告",
    }


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """删除用户及其全部数据（级联，不可恢复）。"""
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除自己")
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    username = target.username
    await AdminService(session).delete_user(user_id)
    return {"message": f"用户 {username} 及其全部数据已删除"}


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    payload: CreateUserIn,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """管理员直接创建账号（用户名 + 初始密码，转告用户）。"""
    _ = current_user
    try:
        user = await AdminService(session).create_user(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"username": user.username, "message": f"账号 {user.username} 已创建"}


# ---------- 目标管理（跨用户 CRUD） ----------


@router.get("/goals")
async def admin_goals(
    limit: int = 100,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    _ = current_user
    return await AdminService(session).goals(limit=limit)


@router.patch("/goals/{goal_id}")
async def admin_update_goal(
    goal_id: int,
    payload: GoalUpdateIn,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    _ = current_user
    try:
        await AdminService(session).update_goal(
            goal_id,
            title=payload.title,
            deadline=payload.deadline,
            weekly_hours=payload.weekly_hours,
            status=payload.status,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"message": f"目标 #{goal_id} 已更新"}


@router.delete("/goals/{goal_id}")
async def admin_delete_goal(
    goal_id: int,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    _ = current_user
    try:
        await AdminService(session).delete_goal(goal_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"message": f"目标 #{goal_id} 及其计划任务已删除"}


# ---------- 任务管理（跨用户 CRUD） ----------


@router.get("/tasks")
async def admin_tasks(
    user_id: int | None = None,
    limit: int = 100,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    _ = current_user
    return await AdminService(session).tasks(user_id=user_id, limit=limit)


@router.patch("/tasks/{task_id}")
async def admin_update_task(
    task_id: int,
    payload: TaskUpdateIn,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    _ = current_user
    try:
        await AdminService(session).update_task(
            task_id,
            title=payload.title,
            date=payload.date,
            duration_minutes=payload.duration_minutes,
            status=payload.status,
            skip_reason=payload.skip_reason,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"message": f"任务 #{task_id} 已更新"}


@router.delete("/tasks/{task_id}")
async def admin_delete_task(
    task_id: int,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    _ = current_user
    try:
        await AdminService(session).delete_task(task_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"message": f"任务 #{task_id} 已删除"}


# ---------- 提案：管理员代批/代拒（复用业务 service，与用户操作同一条路径） ----------


@router.post("/proposals/{proposal_id}/approve")
async def admin_approve_proposal(
    proposal_id: int,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    _ = current_user
    from app.services.errors import NotFoundError, StateConflictError
    from app.services.plan_import import PlanImportService

    try:
        await PlanImportService(session).approve_by_admin(proposal_id)
    except (NotFoundError, StateConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"message": f"提案 #{proposal_id} 已由管理员批准，计划生效"}


@router.post("/proposals/{proposal_id}/reject")
async def admin_reject_proposal(
    proposal_id: int,
    payload: AdminRejectIn | None = None,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    _ = current_user
    from app.services.errors import NotFoundError, StateConflictError
    from app.services.plan_import import PlanImportService

    reason = (payload.reason if payload else "") or "管理员代拒"
    try:
        await PlanImportService(session).reject_by_admin(proposal_id, reason)
    except (NotFoundError, StateConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"message": f"提案 #{proposal_id} 已由管理员拒绝（原因：{reason}）"}


@router.get("/reports")
async def admin_reports(
    limit: int = 50,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    _ = current_user
    svc = AdminService(session)
    return await svc.reports(limit)


@router.delete("/reports/{report_id}")
async def admin_delete_report(
    report_id: int,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    _ = current_user
    try:
        await AdminService(session).delete_report(report_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"message": f"周报 #{report_id} 已删除"}


@router.get("/journals")
async def admin_journals(
    limit: int = 50,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    _ = current_user
    return await AdminService(session).journals(limit)


@router.delete("/journals/{journal_id}")
async def admin_delete_journal(
    journal_id: int,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    _ = current_user
    try:
        await AdminService(session).delete_journal(journal_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"message": f"复盘 #{journal_id} 已删除"}


@router.get("/life-logs")
async def admin_life_logs(
    limit: int = 50,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    _ = current_user
    return await AdminService(session).life_logs(limit)


@router.delete("/life-logs/{log_id}")
async def admin_delete_life_log(
    log_id: int,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    _ = current_user
    try:
        await AdminService(session).delete_life_log(log_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"message": f"生活打卡 #{log_id} 已删除"}


@router.get("/notifications")
async def admin_notifications(
    limit: int = 50,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    _ = current_user
    return await AdminService(session).notifications(limit)


@router.delete("/notifications/{notification_id}")
async def admin_delete_notification(
    notification_id: int,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    _ = current_user
    try:
        await AdminService(session).delete_notification(notification_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"message": f"通知 #{notification_id} 已删除"}


# ---------- 用户模型配置：查 + 清 ----------


@router.get("/llm-settings")
async def admin_llm_settings(
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    _ = current_user
    return await AdminService(session).llm_settings()


@router.delete("/llm-settings/{user_id}")
async def admin_clear_llm_settings(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    _ = current_user
    try:
        await AdminService(session).clear_llm_settings(user_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"message": f"用户 #{user_id} 的模型配置已清除（需重新配置才能用 AI）"}
