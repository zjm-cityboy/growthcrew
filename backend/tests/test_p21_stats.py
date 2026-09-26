"""P2.1 统计层测试：热力图/周趋势/卡因分布/时段直方图 + 登出撤销 + 提案列表。"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.agents.scheduler import next_monday
from app.domain.enums import SkipReason, TaskStatus
from app.models.plan import Task
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from tests.test_p1_core import _auth, _create_user, _seed_plan_tasks, _today
from tests.test_p12_agent import FakeBackend, _full_flow_script, _import_with_fake

_CN = ZoneInfo("Asia/Shanghai")
_UTC = ZoneInfo("UTC")


async def _stamp(
    engine: AsyncEngine,
    task_index: int,
    *,
    completed_cn_hour: int | None = None,
    skipped_cn_hour: int | None = None,
) -> None:
    """给种子计划里的第 N 个任务盖完成/跳过时刻（用北京时间指定、按 UTC 落库）。"""
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        from sqlalchemy import select

        result = await session.execute(select(Task).order_by(Task.id))
        tasks = list(result.scalars().all())
        task = tasks[task_index]
        if completed_cn_hour is not None:
            task.completed_at = (
                datetime.combine(_today(), datetime.min.time(), tzinfo=_CN)
                .replace(hour=completed_cn_hour)
                .astimezone(_UTC)
            )
        if skipped_cn_hour is not None:
            task.skipped_at = (
                datetime.combine(_today(), datetime.min.time(), tzinfo=_CN)
                .replace(hour=skipped_cn_hour)
                .astimezone(_UTC)
            )
        await session.commit()


async def test_heatmap_and_trends(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "stats_user")
    headers = _auth(user_id)
    # 上一整个周（与本周期分离，避免今天的数据落进同一周）
    monday = _today() - timedelta(days=_today().weekday()) - timedelta(weeks=1)
    await _seed_plan_tasks(
        engine,
        user_id,
        [
            (monday, "A", TaskStatus.DONE),
            (monday, "B", TaskStatus.DONE),
            (monday, "C", TaskStatus.TODO),
            (monday + timedelta(days=1), "D", TaskStatus.DONE),
            (_today(), "E", TaskStatus.TODO),
        ],
    )

    heat = await client.get("/api/v1/stats/heatmap", params={"weeks": 2}, headers=headers)
    assert heat.status_code == 200
    days = {d["date"]: d for d in heat.json()["days"]}
    assert days[monday.isoformat()] == {"date": monday.isoformat(), "done": 2, "total": 3}
    assert days[_today().isoformat()]["total"] == 1

    trends = await client.get("/api/v1/stats/trends", params={"weeks": 2}, headers=headers)
    weeks = {w["week_start"]: w for w in trends.json()["weeks"]}
    last_full = weeks[monday.isoformat()]
    assert last_full["done"] == 3 and last_full["total"] == 4
    assert last_full["rate"] == 75.0


async def test_skip_reasons_distribution(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "reason_user")
    other = await _create_user(engine, "reason_other")
    headers = _auth(user_id)
    tasks = await _seed_plan_tasks(
        engine,
        user_id,
        [
            (_today(), "跳过1", TaskStatus.SKIPPED),
            (_today(), "跳过2", TaskStatus.SKIPPED),
            (_today(), "疲劳跳过", TaskStatus.SKIPPED),
            (_today(), "完成", TaskStatus.DONE),
        ],
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        for tid, reason in zip(tasks[:3], ["分心", "分心", "疲劳"], strict=True):
            task = await session.get(Task, tid)
            assert task is not None
            task.skip_reason = SkipReason(reason)
        await session.commit()
    # 别人的数据不应混入
    await _seed_plan_tasks(engine, other, [(_today(), "别人跳过", TaskStatus.SKIPPED)])

    resp = await client.get("/api/v1/stats/skip-reasons", params={"days": 30}, headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [(i["reason"], i["count"], i["pct"]) for i in items] == [
        ("分心", 2, 66.7),
        ("疲劳", 1, 33.3),
    ]


async def test_hours_histogram_cn_timezone(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "hours_user")
    headers = _auth(user_id)
    await _seed_plan_tasks(
        engine,
        user_id,
        [
            (_today(), "晚上完成", TaskStatus.DONE),
            (_today(), "晚上跳过", TaskStatus.SKIPPED),
        ],
    )
    # 北京 22:30 完成 / 北京 21:00 跳过（换算成 UTC 落库）
    await _stamp(engine, 0, completed_cn_hour=22)
    await _stamp(engine, 1, skipped_cn_hour=21)

    resp = await client.get("/api/v1/stats/hours", params={"days": 30}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["completion_hours"][22] == 1 and sum(body["completion_hours"]) == 1
    assert body["skip_hours"][21] == 1 and sum(body["skip_hours"]) == 1


async def test_logout_revokes_refresh(client: AsyncClient, engine: AsyncEngine) -> None:
    """登出后旧 refresh 必须失效（服务端撤销，ADR-0004 债务清偿）。"""
    user_id = await _create_user(engine, "logout_user")
    headers = _auth(user_id)
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "logout_user", "password": "super-secret-1"},
    )
    refresh = login.json()["refresh_token"]

    out = await client.post("/api/v1/auth/logout", headers=headers)
    assert out.status_code == 204

    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert replay.status_code == 401

    # 重新登录不受影响
    again = await client.post(
        "/api/v1/auth/login",
        json={"username": "logout_user", "password": "super-secret-1"},
    )
    assert again.status_code == 200


async def test_proposals_list(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "plist_user")
    headers = _auth(user_id)
    from tests.test_p12_agent import _create_goal

    goal_id = await _create_goal(client, user_id)
    script_a = _full_flow_script(next_monday(_today()).isoformat(), _today().isoformat())
    first = await _import_with_fake(
        client, engine, user_id, goal_id, FakeBackend(script_a), weekly_hours=10
    )
    second = await _import_with_fake(
        client, engine, user_id, goal_id, FakeBackend(_full_flow_script("2026-10-05", "2026-09-23"))
    )
    assert second["status"] == "proposal"

    resp = await client.get("/api/v1/proposals", headers=headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert items[0]["id"] == second["proposal_id"]  # 新的在前
    assert items[1]["id"] == first["proposal_id"]
    assert items[0]["version"] >= items[1]["version"]
