"""P1 数据层测试：目标 / 今日聚合 / 打卡 / 卡因 / 生活三打卡 / 晚间复盘 / 通知。

日期统一在测试体内取当天（today_cn），避免模块级常量在跨午夜运行时漂移。
"""

from datetime import UTC, date, datetime, timedelta

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.core.time import today_cn
from app.domain.enums import NotificationType, PlanStatus, TaskStatus
from app.models.goal import Goal
from app.models.plan import Task, WeeklyPlan
from app.repositories.notification import NotificationRepository
from app.repositories.user import UserRepository
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


def _auth(user_id: int) -> dict[str, str]:
    token = create_access_token(user_id, get_settings())
    return {"Authorization": f"Bearer {token}"}


def _today() -> date:
    return today_cn()


async def _create_user(engine: AsyncEngine, username: str) -> int:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        user = await UserRepository(session).create(username, hash_password("super-secret-1"))
        await session.commit()
        return user.id


async def _seed_plan_tasks(
    engine: AsyncEngine,
    user_id: int,
    items: list[tuple[date, str, TaskStatus]],
    plan_status: PlanStatus = PlanStatus.ACTIVE,
) -> list[int]:
    """建一个目标 + 周计划（指定状态）+ 若干任务，返回任务 id 列表。"""
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        goal = Goal(user_id=user_id, title="秋招冲刺", category="项目")
        session.add(goal)
        await session.flush()
        plan = WeeklyPlan(goal_id=goal.id, week_start=_today(), status=plan_status, version=1)
        session.add(plan)
        await session.flush()
        task_ids: list[int] = []
        for day, title, status in items:
            task = Task(weekly_plan_id=plan.id, date=day, title=title, status=status)
            if status == TaskStatus.DONE:
                task.completed_at = datetime.now(UTC)
            session.add(task)
            await session.flush()
            task_ids.append(task.id)
        await session.commit()
        return task_ids


async def test_goal_crud(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "goal_user")
    resp = await client.post(
        "/api/v1/goals",
        json={"title": "软考高级", "category": "备考", "deadline": "2026-11-15"},
        headers=_auth(user_id),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "软考高级"
    assert body["status"] == "进行中"
    assert body["milestones"] == []

    listed = await client.get("/api/v1/goals", headers=_auth(user_id))
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    other = await _create_user(engine, "goal_other")
    missing = await client.get(f"/api/v1/goals/{body['id']}", headers=_auth(other))
    assert missing.status_code == 404  # 跨用户不可见，不泄露存在性


async def test_today_aggregate_and_streak(client: AsyncClient, engine: AsyncEngine) -> None:
    today = _today()
    yesterday = today - timedelta(days=1)
    user_id = await _create_user(engine, "today_user")
    # 生效计划：前天/昨天/今天各 1 件完成（streak=3）；昨天 1 件待办；今天 3 件（1 完成 2 待办）
    await _seed_plan_tasks(
        engine,
        user_id,
        [
            (today - timedelta(days=2), "读笔记", TaskStatus.DONE),
            (yesterday, "刷题", TaskStatus.DONE),
            (yesterday, "投简历", TaskStatus.TODO),
            (today, "复习数学", TaskStatus.DONE),
            (today, "英语阅读", TaskStatus.TODO),
            (today, "项目复盘", TaskStatus.TODO),
        ],
    )
    # 草稿计划的今日与昨日任务：列表不可见、统计不计入
    await _seed_plan_tasks(
        engine,
        user_id,
        [
            (today, "草稿任务", TaskStatus.TODO),
            (yesterday, "草稿昨日", TaskStatus.DONE),
        ],
        plan_status=PlanStatus.DRAFT,
    )
    # 已替代版本的昨日完成：历史事实保留在统计里（streak 按 distinct 日期天然去重）
    await _seed_plan_tasks(
        engine,
        user_id,
        [(yesterday, "旧版任务", TaskStatus.DONE)],
        plan_status=PlanStatus.SUPERSEDED,
    )

    resp = await client.get("/api/v1/today", headers=_auth(user_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["yesterday"] == {"done": 2, "total": 3}  # 刷题+旧版 完成；草稿不计
    assert len(body["tasks"]) == 3  # 今日列表只含生效计划
    assert body["journal_submitted"] is False
    assert body["streak"] == 3


async def test_streak_continues_from_yesterday_when_today_empty(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    """今天还没打卡不打断 streak：清晨看仍是连续的（从昨天回溯）。"""
    today = _today()
    user_id = await _create_user(engine, "streak_user")
    await _seed_plan_tasks(
        engine,
        user_id,
        [
            (today - timedelta(days=1), "昨日完成", TaskStatus.DONE),
            (today - timedelta(days=2), "前日完成", TaskStatus.DONE),
            (today, "今日待办", TaskStatus.TODO),
        ],
    )
    resp = await client.get("/api/v1/today", headers=_auth(user_id))
    assert resp.json()["streak"] == 2


async def test_task_complete_and_conflicts(client: AsyncClient, engine: AsyncEngine) -> None:
    today = _today()
    user_id = await _create_user(engine, "task_user")
    todo_id, done_id, skipped_id = await _seed_plan_tasks(
        engine,
        user_id,
        [
            (today, "待办", TaskStatus.TODO),
            (today, "已完成", TaskStatus.DONE),
            (today, "已跳过", TaskStatus.SKIPPED),
        ],
    )

    # 打卡成功并自报时长（空 body 也合法：打卡按钮常不带参数）
    resp = await client.post(
        f"/api/v1/tasks/{todo_id}/complete",
        json={"actual_minutes": 40},
        headers=_auth(user_id),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"
    assert resp.json()["actual_minutes"] == 40

    again = await client.post(f"/api/v1/tasks/{todo_id}/complete", headers=_auth(user_id))
    assert again.status_code == 200  # 幂等

    conflict = await client.post(f"/api/v1/tasks/{skipped_id}/complete", headers=_auth(user_id))
    assert conflict.status_code == 409  # 已跳过的不能完成

    skip_done = await client.post(
        f"/api/v1/tasks/{done_id}/skip", json={"reason": "分心"}, headers=_auth(user_id)
    )
    assert skip_done.status_code == 409  # 已完成的不能跳过


async def test_task_skip_with_reason(client: AsyncClient, engine: AsyncEngine) -> None:
    today = _today()
    user_id = await _create_user(engine, "skip_user")
    task_id, _ = await _seed_plan_tasks(
        engine, user_id, [(today, "政治背诵", TaskStatus.TODO), (today, "占位", TaskStatus.TODO)]
    )

    resp = await client.post(
        f"/api/v1/tasks/{task_id}/skip", json={"reason": "疲劳"}, headers=_auth(user_id)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"
    assert resp.json()["skip_reason"] == "疲劳"

    invalid = await client.post(
        f"/api/v1/tasks/{task_id}/skip", json={"reason": "不想做"}, headers=_auth(user_id)
    )
    assert invalid.status_code == 422  # 卡因四选一之外一律拒绝


async def test_task_cross_user_invisible(client: AsyncClient, engine: AsyncEngine) -> None:
    owner = await _create_user(engine, "owner_user")
    intruder = await _create_user(engine, "intruder_user")
    task_id, _ = await _seed_plan_tasks(
        engine,
        owner,
        [(_today(), "机密任务", TaskStatus.TODO), (_today(), "占位", TaskStatus.TODO)],
    )
    resp = await client.post(f"/api/v1/tasks/{task_id}/complete", headers=_auth(intruder))
    assert resp.status_code == 404


async def test_life_log_upsert_merge_and_backfill(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "life_user")

    first = await client.post(
        "/api/v1/life-logs",
        json={"sleep_hours": 6.5, "exercise": True},
        headers=_auth(user_id),
    )
    assert first.status_code == 200
    assert first.json()["exercise"] is True

    # 第二次只补心情：已有字段不被覆盖
    second = await client.post("/api/v1/life-logs", json={"mood": 4}, headers=_auth(user_id))
    assert second.status_code == 200
    body = second.json()
    assert body["sleep_hours"] == 6.5
    assert body["exercise"] is True
    assert body["mood"] == 4

    # 显式指定日期：补录昨天（不影响今天的记录）
    backfill_day = (_today() - timedelta(days=1)).isoformat()
    backfill = await client.post(
        "/api/v1/life-logs",
        json={"date": backfill_day, "sleep_hours": 7.0},
        headers=_auth(user_id),
    )
    assert backfill.status_code == 200
    assert backfill.json()["date"] == backfill_day
    assert backfill.json()["mood"] is None

    empty = await client.post("/api/v1/life-logs", json={}, headers=_auth(user_id))
    assert empty.status_code == 422


async def test_journal_flow(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "journal_user")
    await _seed_plan_tasks(
        engine,
        user_id,
        [
            (_today(), "做完的", TaskStatus.DONE),
            (_today(), "没做的", TaskStatus.TODO),
        ],
    )

    state = await client.get("/api/v1/journals/today", headers=_auth(user_id))
    assert state.status_code == 200
    assert state.json() == {
        "submitted": False,
        "mood": None,
        "note": None,
        "today_done": 1,
        "today_total": 2,
    }

    submitted = await client.post(
        "/api/v1/journals/today", json={"mood": 4, "note": "状态不错"}, headers=_auth(user_id)
    )
    assert submitted.status_code == 200
    assert submitted.json()["submitted"] is True

    resubmit = await client.post(
        "/api/v1/journals/today", json={"mood": 3, "note": "改一下"}, headers=_auth(user_id)
    )
    assert resubmit.status_code == 200
    assert resubmit.json()["mood"] == 3


async def test_notifications_flow(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "notify_user")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        repo = NotificationRepository(session)
        await repo.create(
            user_id, NotificationType.MORNING_BRIEF, "昨日完成 2/3", "英语阅读挪到今天"
        )
        unread = await repo.create(
            user_id, NotificationType.PROPOSAL, "教练的新周计划提案", "等你审批"
        )
        # 已读且更早的一条：排序应排在未读之后
        older = await repo.create(user_id, NotificationType.SYSTEM, "旧通知", "")
        older.read = True
        await session.commit()
        older_id, unread_id = older.id, unread.id

    listed = await client.get("/api/v1/notifications", headers=_auth(user_id))
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 3
    assert items[0]["id"] == unread_id  # 未读优先，同组内新的在前
    assert items[-1]["id"] == older_id

    read_resp = await client.post(f"/api/v1/notifications/{unread_id}/read", headers=_auth(user_id))
    assert read_resp.status_code == 200
    assert read_resp.json()["read"] is True

    intruder = await _create_user(engine, "notify_intruder")
    forbidden = await client.post(
        f"/api/v1/notifications/{unread_id}/read", headers=_auth(intruder)
    )
    assert forbidden.status_code == 404
