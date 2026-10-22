"""晨间摘要与晚间提醒任务体（可独立于调度器测试）。

健壮性约定：
- 当日去重：每用户每类型每天最多一条（多 worker 误开/手动补跑的代码级兜底）；
- 单点隔离：单个用户处理失败只记日志回滚本人，不影响其他人；
- 零 LLM：模板 + SQL 聚合（ADR-0002：管家不是 Agent）。
将来接微信/Bark 通道时只需在此处追加推送适配器，任务体不变。
"""

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.time import cn_day_start_utc_naive, today_cn
from app.domain.enums import NotificationType
from app.repositories.journal import JournalRepository
from app.repositories.notification import NotificationRepository
from app.repositories.plan import TaskRepository
from app.repositories.user import UserRepository
from app.schemas.today import TodayOut
from app.services.push import notify_and_push
from app.services.today import TodayService

logger = logging.getLogger(__name__)


def render_morning_brief(today: TodayOut, due_mistakes: int = 0) -> tuple[str, str]:
    """模板渲染（纯函数）：返回 (标题, 正文)。"""
    mistake_line = f"\n📖 {due_mistakes} 道错题到期" if due_mistakes > 0 else ""
    if today.tasks:
        lines = "\n".join(f"{i}. {task.title}" for i, task in enumerate(today.tasks[:3], start=1))
        yesterday = (
            f"昨天完成 {today.yesterday.done}/{today.yesterday.total}。"
            if today.yesterday.total and today.yesterday.done > 0
            else ""
        )
        more = f"\n…共 {len(today.tasks)} 件" if len(today.tasks) > 3 else ""
        return (
            f"早上好，今天 {len(today.tasks)}件事"
            + (f"，{due_mistakes} 道错题" if due_mistakes else ""),
            f"{yesterday}今天：\n{lines}{more}{mistake_line}",
        )
    if due_mistakes:
        return f"早上好，{due_mistakes} 道错题到期", f"今天没有安排任务。{mistake_line.strip()}"
    return "早上好", "今天还没有安排。去「对话」贴入参考计划，教练帮你排进今天。"


async def morning_brief_job(session_maker: async_sessionmaker[AsyncSession]) -> int:
    """为所有用户生成晨间摘要通知（当日去重 + 单点隔离），返回成功条数。"""
    created = 0
    failed = 0
    async with session_maker() as session:
        users = await UserRepository(session).list_all()
        since = cn_day_start_utc_naive(today_cn())
        for user in users:
            try:
                notifications = NotificationRepository(session)
                if await notifications.exists_since(user.id, NotificationType.MORNING_BRIEF, since):
                    continue  # 今天已发过
                today = await TodayService(session).get(user.id)
                from app.repositories.mistake import MistakeRepository

                due = await MistakeRepository(session).count_due(user.id, today_cn())
                title, body = render_morning_brief(today, due)
                await notify_and_push(session, user.id, NotificationType.MORNING_BRIEF, title, body)
                await session.commit()
                created += 1
            except Exception:
                await session.rollback()
                failed += 1
                logger.exception("晨推失败 user_id=%s", user.id)
    logger.info("morning_brief done sent=%d failed=%d", created, failed)
    return created


async def _evening_body(session: AsyncSession, user_id: int) -> str:
    """数据感知的晚间文案：看今天剩什么 + 本周跳过规律，分场景说话。

    这是"主动管家"的确定性部分（ADR-0002：文案分支走数据，不硬上 LLM）；
    连续同因跳过的场景里，承诺的调整在下次生成计划时由教练真实兑现。
    """
    day = today_cn()
    done, total = await TaskRepository(session).day_summary(user_id, day)
    todo = total - done
    # 口径与跳过响应的 coach_hint 一致：周一至今（而不是滚动 7 天窗，
    # 那会把上周的数据混进"这周你已 N 次"，两处数字对不上）
    skip_counts = {
        reason.value: count for reason, count in await _skip_counts_this_week(session, user_id)
    }
    top_reason, top_count = (
        max(skip_counts.items(), key=lambda kv: kv[1]) if skip_counts else (None, 0)
    )

    if todo > 0 and top_count >= 3:
        return (
            f"今天还有 {todo} 件没完成——这周你已 {top_count} 次因「{top_reason}」跳过，"
            "别硬撑。跳过时如实选原因，明天生成计划时我会自动给你减量。"
        )
    if todo > 0:
        return f"今天还剩 {todo} 件（已完成 {done}/{total}）。做不完没关系，跳过时告诉我原因就好。"
    if total > 0:
        return f"今天 {total} 件全部完成 ✅ 来写个一分钟复盘，记录这个好状态。"
    return "今天状态几分？打开「今日」，一分钟记录一下就休息。"


async def _skip_counts_this_week(session: AsyncSession, user_id: int) -> list[tuple[Any, int]]:
    """本周（周一至今）各跳过原因的次数，计划状态口径与统计一致。"""
    from sqlalchemy import func as sa_func
    from sqlalchemy import select as sa_select

    from app.domain.constants import COUNTED_PLAN_STATUSES
    from app.models.goal import Goal
    from app.models.plan import Task, WeeklyPlan

    monday = today_cn() - timedelta(days=today_cn().weekday())
    rows = (
        await session.execute(
            sa_select(Task.skip_reason, sa_func.count())
            .join(WeeklyPlan, Task.weekly_plan_id == WeeklyPlan.id)
            .join(Goal, WeeklyPlan.goal_id == Goal.id)
            .where(
                Task.date >= monday,
                Task.date <= today_cn(),
                Goal.user_id == user_id,
                Task.skip_reason.is_not(None),
                WeeklyPlan.status.in_(COUNTED_PLAN_STATUSES),
            )
            .group_by(Task.skip_reason)
        )
    ).all()
    return [(reason, int(count)) for reason, count in rows]


async def evening_reminder_job(session_maker: async_sessionmaker[AsyncSession]) -> int:
    """晚间轻复盘提醒：只提醒还没写复盘的用户（当日去重 + 单点隔离）。

    文案是数据感知的：剩余任务量与本周跳过规律决定说什么（见 _evening_body）。
    """
    created = 0
    failed = 0
    async with session_maker() as session:
        users = await UserRepository(session).list_all()
        journals = JournalRepository(session)
        notifications = NotificationRepository(session)
        day = today_cn()
        since = cn_day_start_utc_naive(day)
        for user in users:
            try:
                if await journals.get(user.id, day) is not None:
                    continue  # 已写复盘不打扰
                if await notifications.exists_since(
                    user.id, NotificationType.EVENING_REMINDER, since
                ):
                    continue
                await notify_and_push(
                    session,
                    user.id,
                    NotificationType.EVENING_REMINDER,
                    "晚间一分钟",
                    await _evening_body(session, user.id),
                )
                await session.commit()
                created += 1
            except Exception:
                await session.rollback()
                failed += 1
                logger.exception("晚间提醒失败 user_id=%s", user.id)
    logger.info("evening_reminder done sent=%d failed=%d", created, failed)
    return created
