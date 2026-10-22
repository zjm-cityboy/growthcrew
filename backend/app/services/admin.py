"""管理后台业务：部署者视角的全系统数据（用户/统计/提案审计）。

权限在 API 层守卫（用户名 ∈ GC_ADMIN_USERNAMES）；本层只做聚合查询，
复用 DataResetService 清数据（与用户自助清空同一条路径）。
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.domain.enums import GoalStatus, PlanStatus, TaskStatus
from app.models.goal import Goal
from app.models.journal import DailyJournal, LifeLog
from app.models.llm_settings import UserLLMSettings
from app.models.notification import Notification
from app.models.plan import PlanProposal, Task, WeeklyPlan
from app.models.report import WeeklyReport
from app.models.user import User
from app.services.data_reset import DataResetService

# 管理员重置密码时生成的随机密码长度（返回给管理员展示一次）
_TEMP_PASSWORD_LENGTH = 12


def _jsonable(value: Any) -> Any:
    """datetime/date → ISO 字符串（记录列表直出 JSON 用）。"""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class AdminUserRow:
    id: int
    username: str
    created_at: object
    is_active: bool
    goals: int
    active_goals: int
    tasks_total: int
    tasks_done: int
    llm_configured: bool


@dataclass(frozen=True)
class AdminOverview:
    users: int
    goals: int
    tasks_total: int
    tasks_done: int
    proposals: int
    reports: int
    journals: int
    life_logs: int


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def overview(self) -> AdminOverview:
        async def count(stmt: Select[tuple[int]]) -> int:
            return int((await self._session.execute(stmt)).scalar() or 0)

        return AdminOverview(
            users=await count(select(func.count()).select_from(User)),
            goals=await count(select(func.count()).select_from(Goal)),
            tasks_total=await count(select(func.count()).select_from(Task)),
            tasks_done=await count(
                select(func.count()).select_from(Task).where(Task.status == TaskStatus.DONE)
            ),
            proposals=await count(select(func.count()).select_from(PlanProposal)),
            reports=await count(select(func.count()).select_from(WeeklyReport)),
            journals=await count(select(func.count()).select_from(DailyJournal)),
            life_logs=await count(select(func.count()).select_from(LifeLog)),
        )

    async def users(self) -> list[AdminUserRow]:
        configured_ids = set(
            (await self._session.execute(select(UserLLMSettings.user_id))).scalars().all()
        )
        rows: list[AdminUserRow] = []
        users = list((await self._session.execute(select(User).order_by(User.id))).scalars().all())
        for user in users:
            goals = int(
                (
                    await self._session.execute(
                        select(func.count()).select_from(Goal).where(Goal.user_id == user.id)
                    )
                ).scalar()
                or 0
            )
            active_goals = int(
                (
                    await self._session.execute(
                        select(func.count())
                        .select_from(Goal)
                        .where(Goal.user_id == user.id, Goal.status == GoalStatus.ACTIVE)
                    )
                ).scalar()
                or 0
            )
            task_stats = (
                await self._session.execute(
                    select(func.count(), func.sum(Task.status == TaskStatus.DONE))
                    .select_from(Task)
                    .join(WeeklyPlan, Task.weekly_plan_id == WeeklyPlan.id)
                    .join(Goal, WeeklyPlan.goal_id == Goal.id)
                    .where(Goal.user_id == user.id)
                )
            ).one()
            rows.append(
                AdminUserRow(
                    id=user.id,
                    username=user.username,
                    created_at=user.created_at,
                    is_active=user.is_active,
                    goals=goals,
                    active_goals=active_goals,
                    tasks_total=int(task_stats[0] or 0),
                    tasks_done=int(task_stats[1] or 0),
                    llm_configured=user.id in configured_ids,
                )
            )
        return rows

    async def proposals(self, limit: int = 30) -> list[dict[str, object]]:
        """全系统提案审计（含归属用户与拒绝原因——管理视角的核心表）。"""
        result = await self._session.execute(
            select(PlanProposal, Goal, User)
            .join(WeeklyPlan, PlanProposal.weekly_plan_id == WeeklyPlan.id)
            .join(Goal, WeeklyPlan.goal_id == Goal.id)
            .join(User, Goal.user_id == User.id)
            .order_by(PlanProposal.id.desc())
            .limit(limit)
        )
        return [
            {
                "id": prop.id,
                "username": user.username,
                "goal_title": goal.title,
                "status": prop.status.value,
                "rejection_reason": prop.rejection_reason,
                "created_at": prop.created_at.isoformat(),
                "summary": str((prop.diff or {}).get("summary", ""))[:80],
            }
            for prop, goal, user in result.all()
        ]

    async def reset_user_history(self, target_user_id: int) -> int:
        """清空指定用户的执行历史（管理动作，与用户自助清空同一条路径）。"""
        return await DataResetService(self._session).reset_history(target_user_id)

    async def set_user_active(self, target_user_id: int, active: bool) -> None:
        """禁用/启用账号：禁用后无法登录、已有令牌立即失效（get_active_user 拦截）。

        禁用时同步吊销全部刷新令牌——否则禁用→再启用后，禁用期间签发的
        旧 refresh token 会复活（refresh 校验只看当前 is_active，不回看历史）。
        """
        user = await self._session.get(User, target_user_id)
        if user is None:
            raise LookupError("用户不存在")
        user.is_active = active
        if not active:
            from app.repositories.user import RefreshTokenRepository

            await RefreshTokenRepository(self._session).revoke_all_for_user(target_user_id)
        await self._session.commit()

    async def reset_user_password(self, target_user_id: int) -> str:
        """重置用户密码为随机临时密码，返回给管理员转告（仅此一次可见）。

        同步吊销全部刷新令牌：重置密码通常是凭据泄露的应急处置，
        不吊销的话攻击者手里的 refresh token（30 天有效）仍可持续轮换。
        """
        import secrets
        import string

        user = await self._session.get(User, target_user_id)
        if user is None:
            raise LookupError("用户不存在")
        alphabet = string.ascii_letters + string.digits
        temp_password = "".join(secrets.choice(alphabet) for _ in range(_TEMP_PASSWORD_LENGTH))
        user.password_hash = hash_password(temp_password)
        from app.repositories.user import RefreshTokenRepository

        await RefreshTokenRepository(self._session).revoke_all_for_user(target_user_id)
        await self._session.commit()
        return temp_password

    async def delete_user(self, target_user_id: int) -> None:
        """删除用户及其全部数据（数据库级联 CASCADE；不可恢复，前端须两步确认）。"""
        user = await self._session.get(User, target_user_id)
        if user is None:
            raise LookupError("用户不存在")
        await self._session.delete(user)
        await self._session.commit()

    async def create_user(self, username: str, password: str) -> User:
        """管理员直接创建账号（密码由管理员设定并转告用户）。"""
        existing = (
            await self._session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError("用户名已存在")
        user = User(username=username, password_hash=hash_password(password))
        self._session.add(user)
        await self._session.commit()
        return user

    # ---------- 目标管理（跨用户 CRUD） ----------

    async def goals(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = (
            await self._session.execute(
                select(Goal, User).join(User).order_by(Goal.id.desc()).limit(limit)
            )
        ).all()
        return [
            {
                "id": goal.id,
                "username": user.username,
                "title": goal.title,
                "category": goal.category.value,
                "status": goal.status.value,
                "deadline": goal.deadline.isoformat() if goal.deadline else None,
                "weekly_hours": goal.weekly_hours,
            }
            for goal, user in rows
        ]

    async def update_goal(self, goal_id: int, **fields: Any) -> Goal:
        """可改字段：title/deadline/weekly_hours/status。

        业务级联：状态离开"进行中"的任何迁移（归档/完成）都停排生效中计划
        ——否则任务还会出现在用户今日页，形成"不执行了还在执行"的矛盾。
        反向切回"进行中"不停排（旧计划仍是被替代态，需重新生成）。
        """
        goal = await self._session.get(Goal, goal_id)
        if goal is None:
            raise LookupError("目标不存在")
        was_active = goal.status == GoalStatus.ACTIVE
        for key in ("title", "deadline", "weekly_hours", "status"):
            if key in fields and fields[key] is not None:
                setattr(goal, key, fields[key])
        if was_active and goal.status != GoalStatus.ACTIVE:
            await self._session.execute(
                update(WeeklyPlan)
                .where(WeeklyPlan.goal_id == goal_id, WeeklyPlan.status == PlanStatus.ACTIVE)
                .values(status=PlanStatus.SUPERSEDED)
            )
        await self._session.commit()
        return goal

    async def delete_goal(self, goal_id: int) -> None:
        goal = await self._session.get(Goal, goal_id)
        if goal is None:
            raise LookupError("目标不存在")
        await self._session.delete(goal)
        await self._session.commit()

    # ---------- 任务管理（跨用户 CRUD） ----------

    async def tasks(self, user_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        stmt = (
            select(Task, Goal, User)
            .join(WeeklyPlan, Task.weekly_plan_id == WeeklyPlan.id)
            .join(Goal, WeeklyPlan.goal_id == Goal.id)
            .join(User)
            .order_by(Task.id.desc())
            .limit(limit)
        )
        if user_id is not None:
            stmt = stmt.where(User.id == user_id)
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "id": task.id,
                "username": user.username,
                "goal_title": goal.title,
                "date": task.date.isoformat(),
                "title": task.title,
                "duration_minutes": task.duration_minutes,
                "status": task.status.value,
                "skip_reason": task.skip_reason.value if task.skip_reason else None,
            }
            for task, goal, user in rows
        ]

    async def update_task(self, task_id: int, **fields: Any) -> Task:
        """可改字段：title/date/duration_minutes/status/skip_reason（管理端纠错用）。

        状态变更同步维护 completed_at/skipped_at 时间戳（与用户端打卡同规则）
        ——否则管理员代改 done 的任务进不了小时分布统计（统计过滤
        completed_at IS NOT NULL）。
        """
        from datetime import UTC, datetime

        task = await self._session.get(Task, task_id)
        if task is None:
            raise LookupError("任务不存在")
        old_status = task.status
        for key in ("title", "date", "duration_minutes", "status", "skip_reason"):
            if key in fields:
                setattr(task, key, fields[key])
        if "status" in fields and task.status != old_status:
            now = datetime.now(UTC)
            if task.status == TaskStatus.DONE:
                task.completed_at = now
                task.skipped_at = None
            elif task.status == TaskStatus.SKIPPED:
                task.skipped_at = now
                task.completed_at = None
            else:  # 改回待办：清两戳，回到未执行状态
                task.completed_at = None
                task.skipped_at = None
        await self._session.commit()
        return task

    async def delete_task(self, task_id: int) -> None:
        task = await self._session.get(Task, task_id)
        if task is None:
            raise LookupError("任务不存在")
        await self._session.delete(task)
        await self._session.commit()

    # ---------- 记录类实体（周报/复盘/生活打卡/通知）：查 + 删 ----------

    async def _list_with_user(self, model: Any, limit: int) -> list[dict[str, Any]]:
        """通用列表：任意带 user_id 的记录表，附用户名（记录类管理的统一形态）。"""
        rows = (
            await self._session.execute(
                select(model, User)
                .join(User, model.user_id == User.id)
                .order_by(model.id.desc())
                .limit(limit)
            )
        ).all()
        out = []
        for row, user in rows:
            item = {c.name: _jsonable(getattr(row, c.name)) for c in model.__table__.columns}
            item["username"] = user.username
            out.append(item)
        return out

    async def _delete_by_id(self, model: Any, row_id: int, label: str) -> None:
        row = await self._session.get(model, row_id)
        if row is None:
            raise LookupError(f"{label}不存在")
        await self._session.delete(row)
        await self._session.commit()

    async def reports(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self._list_with_user(WeeklyReport, limit)

    async def delete_report(self, report_id: int) -> None:
        await self._delete_by_id(WeeklyReport, report_id, "周报")

    async def journals(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self._list_with_user(DailyJournal, limit)

    async def delete_journal(self, journal_id: int) -> None:
        await self._delete_by_id(DailyJournal, journal_id, "复盘")

    async def life_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self._list_with_user(LifeLog, limit)

    async def delete_life_log(self, log_id: int) -> None:
        await self._delete_by_id(LifeLog, log_id, "生活打卡")

    async def notifications(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self._list_with_user(Notification, limit)

    async def delete_notification(self, notification_id: int) -> None:
        await self._delete_by_id(Notification, notification_id, "通知")

    # ---------- 用户模型配置：查 + 清 ----------

    async def llm_settings(self) -> list[dict[str, Any]]:
        """全部用户的模型配置概览（密钥只显示已配置，不泄露内容）。"""
        rows = (await self._session.execute(select(UserLLMSettings, User).join(User))).all()
        return [
            {
                "user_id": s.user_id,
                "username": u.username,
                "base_url": s.base_url,
                "model_name": s.model_name,
                "updated_at": _jsonable(s.updated_at),
            }
            for s, u in rows
        ]

    async def clear_llm_settings(self, user_id: int) -> None:
        """清除某用户的模型配置（密钥轮换失效/用户要求删除时用）。"""
        row = (
            await self._session.execute(
                select(UserLLMSettings).where(UserLLMSettings.user_id == user_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("该用户没有模型配置")
        await self._session.delete(row)
        await self._session.commit()
