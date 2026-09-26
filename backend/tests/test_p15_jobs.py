"""P1.5 定时任务测试：晨间摘要与晚间提醒（零 LLM，任务体直测）。"""

from app.core.config import get_settings
from app.core.time import today_cn
from app.domain.enums import NotificationType, TaskStatus
from app.jobs.briefs import evening_reminder_job, morning_brief_job, render_morning_brief
from app.jobs.scheduler import build_scheduler
from app.repositories.journal import JournalRepository
from app.repositories.notification import NotificationRepository
from app.schemas.task import TaskOut
from app.schemas.today import DaySummaryOut, TodayOut
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from tests.test_p1_core import _create_user, _seed_plan_tasks, _today


def _task(task_id: int, title: str) -> TaskOut:
    return TaskOut(
        id=task_id,
        date=_today(),
        title=title,
        duration_minutes=90,
        category_label="",
        status="todo",
        skip_reason=None,
        actual_minutes=None,
        completed_at=None,
    )


def test_render_morning_brief_with_tasks() -> None:
    today = TodayOut(
        date=_today(),
        yesterday=DaySummaryOut(done=2, total=3),
        tasks=[_task(1, "数学 · 专注 90 分钟"), _task(2, "英语阅读")],
        life_log=None,
        journal_submitted=False,
        streak=5,
    )
    title, body = render_morning_brief(today)
    assert title == "早上好，今天 2件事"
    assert "昨天完成 2/3。" in body
    assert "1. 数学 · 专注 90 分钟" in body


def test_render_morning_brief_empty_day() -> None:
    today = TodayOut(
        date=_today(),
        yesterday=DaySummaryOut(done=0, total=0),
        tasks=[],
        life_log=None,
        journal_submitted=False,
        streak=0,
    )
    title, body = render_morning_brief(today)
    assert title == "早上好"
    assert "还没有安排" in body


async def test_morning_brief_job_creates_notification(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    user_id = await _create_user(engine, "brief_user")
    await _seed_plan_tasks(
        engine,
        user_id,
        [
            (_today(), "数学 · 专注 90 分钟", TaskStatus.TODO),
            (_today(), "英语阅读", TaskStatus.TODO),
        ],
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    created = await morning_brief_job(maker)
    assert created == 1

    async with maker() as session:
        items = await NotificationRepository(session).list_for_user(user_id)
    briefs = [n for n in items if n.type == NotificationType.MORNING_BRIEF]
    assert len(briefs) == 1
    assert "2件事" in briefs[0].title
    assert "数学 · 专注 90 分钟" in briefs[0].body


async def test_morning_brief_empty_day_gentle_nudge(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    user_id = await _create_user(engine, "brief_empty_user")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    await morning_brief_job(maker)

    async with maker() as session:
        items = await NotificationRepository(session).list_for_user(user_id)
    assert any("还没有安排" in n.body for n in items)


async def test_evening_reminder_only_for_unsubmitted(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    user_a = await _create_user(engine, "evening_a")
    user_b = await _create_user(engine, "evening_b")
    maker = async_sessionmaker(engine, expire_on_commit=False)

    # a 已写复盘，b 未写：只提醒 b
    async with maker() as session:
        await JournalRepository(session).upsert(user_a, today_cn(), 4, "不错")
        await session.commit()

    created = await evening_reminder_job(maker)
    assert created == 1

    async with maker() as session:
        items_a = await NotificationRepository(session).list_for_user(user_a)
        items_b = await NotificationRepository(session).list_for_user(user_b)
    assert any(n.title == "晚间一分钟" for n in items_b)
    assert not any(n.title == "晚间一分钟" for n in items_a)


def test_build_scheduler_registers_both_jobs() -> None:
    scheduler = build_scheduler(async_sessionmaker(), get_settings())
    job_ids = {job.id for job in scheduler.get_jobs()}
    # P2.2 起另有两个复盘师 job；此处只验证 P1.5 的两个仍在
    assert {"morning_brief", "evening_reminder"} <= job_ids


def test_render_morning_brief_zero_done_omits_stats() -> None:
    """昨日 0 完成不提数字：不制造焦虑（产品理念）。"""
    today = TodayOut(
        date=_today(),
        yesterday=DaySummaryOut(done=0, total=5),
        tasks=[_task(1, "数学 · 专注 90 分钟")],
        life_log=None,
        journal_submitted=False,
        streak=0,
    )
    _, body = render_morning_brief(today)
    assert "昨天完成" not in body
    assert "数学" in body


async def test_morning_brief_job_dedupes_same_day(client: AsyncClient, engine: AsyncEngine) -> None:
    """同一天重复执行（多 worker 误开/手动补跑）只发一条。"""
    user_id = await _create_user(engine, "dedup_user")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    first = await morning_brief_job(maker)
    second = await morning_brief_job(maker)
    assert (first, second) == (1, 0)

    async with maker() as session:
        items = await NotificationRepository(session).list_for_user(user_id)
    assert len([n for n in items if n.type == NotificationType.MORNING_BRIEF]) == 1


async def test_evening_reminder_job_dedupes_same_day(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    await _create_user(engine, "dedup_evening_user")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    assert await evening_reminder_job(maker) == 1
    assert await evening_reminder_job(maker) == 0


def test_schedule_hour_bounds_fail_fast() -> None:
    """提醒时刻越界（如 24 点）应在配置层报错，而不是 apscheduler 深处。"""
    import pytest
    from app.core.config import Settings
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(morning_brief_hour=24)
    with pytest.raises(ValidationError):
        Settings(evening_reminder_hour=-1)
