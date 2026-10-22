# ruff: noqa: S311 - 演示数据用伪随机即可，非密码学场景
"""演示数据回填：面试演示前一键生成数周历史 + 触发一次周报，不用真等一周。

用法（backend 目录下执行）：
  D:/anaconda3/envs/growthcrew/python.exe scripts/seed_demo.py --user Demo
  可选：--subjects "数学,英语,专业课"  --weeks 4  --clean（只清不建）

配合设置页"演示时间快进"（GC_DEMO_MODE）现场演示完整闭环：
  回填（图表/周报立即有数据）→ 现场打卡 → 快进 +1 天 → 今日任务滚动、streak 累积。

数据故事（刻意设计，让图表与周报能挖出洞察）：
- 上午任务 ~85% 完成，晚间任务 ~65% 跳过（卡因以"疲劳"为主）
  → 高效时段图早晚分化，周报可产出"晚间任务大多因疲劳跳过"级洞察；
- 时间戳按"SQLite 朴素值=UTC"的统计口径写入：想呈现北京时间 H 点，写 H-8 点。
"""

import argparse
import asyncio
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 让 scripts/ 能 import app

from app.agents.llm import build_backend_from_byok
from app.agents.reviewer import ReviewerAgent
from app.core.config import get_settings
from app.core.crypto import CryptoError
from app.core.db import create_db_engine, create_session_maker
from app.core.time import today_cn
from app.domain.enums import GoalStatus, PlanStatus, SkipReason, TaskStatus
from app.models.goal import Goal
from app.models.journal import DailyJournal, LifeLog
from app.models.plan import Task, WeeklyPlan
from app.models.report import WeeklyReport
from app.models.user import User
from app.services.llm_settings import LLMSettingsService
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

random.seed(42)  # 固定种子：每次生成的数据形状一致，演示讲稿不用改

# 每天任务的时段安排（北京时间小时，完成率）故事：上午高效、下午正常、晚间大多跳过
_SLOTS: list[tuple[int, float]] = [
    (9, 0.85),
    (15, 0.75),
    (22, 0.35),  # 晚间：跳过为主（疲劳）→ 高效时段图分化 + 周报招牌洞察
]
_SKIP_REASONS = [  # 跳过时的卡因权重：疲劳为主（晚间故事），其余点缀
    (SkipReason.TIRED, 0.6),
    (SkipReason.DISTRACTED, 0.25),
    (SkipReason.TOO_HARD, 0.1),
    (SkipReason.INTERRUPTED, 0.05),
]
_NOTES_POOL = [
    "今天状态不错，按计划走完了",
    "上午效率很高，晚上有点犯困",
    "被杂事打断了几次，明天调整",
    "难度比想的大，多花了点时间",
    "睡眠不够，晚上学不进去",
    "",
]
_DURATIONS = [30, 45, 60]


def _weighted_reason() -> SkipReason:
    pick, acc = random.random(), 0.0
    for reason, weight in _SKIP_REASONS:
        acc += weight
        if pick <= acc:
            return reason
    return _SKIP_REASONS[-1][0]


def _stamp(day: date, cn_hour: int) -> datetime:
    """北京时间 cn_hour 点 → SQLite 朴素 UTC（统计口径：朴素值按 UTC 解释再转北京）。"""
    return datetime.combine(day, time(cn_hour - 8, random.randint(0, 59)))


async def _find(session: AsyncSession, username: str) -> tuple[User, Goal]:
    user = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"用户 {username!r} 不存在，请先在 App 里注册")
    goal = (
        (
            await session.execute(
                select(Goal)
                .where(Goal.user_id == user.id, Goal.status == GoalStatus.ACTIVE)
                .order_by(Goal.id)
                .limit(1)  # 多目标时取最早创建的；演示数据挂在它名下
            )
        )
        .scalars()
        .first()
    )
    if goal is None:
        raise SystemExit("该用户没有进行中的目标：请先创建一个目标（对话页）再回填")
    return user, goal


async def _clean(session: AsyncSession, user_id: int) -> None:
    """清该用户全部历史（任务→计划→生活→复盘→周报），演示数据可反复重建。"""
    await session.execute(
        delete(Task).where(
            Task.weekly_plan_id.in_(select(WeeklyPlan.id).join(Goal).where(Goal.user_id == user_id))
        )
    )
    await session.execute(
        delete(WeeklyPlan).where(
            WeeklyPlan.goal_id.in_(select(Goal.id).where(Goal.user_id == user_id))
        )
    )
    await session.execute(delete(LifeLog).where(LifeLog.user_id == user_id))
    await session.execute(delete(DailyJournal).where(DailyJournal.user_id == user_id))
    await session.execute(delete(WeeklyReport).where(WeeklyReport.user_id == user_id))


_FUTURE_WEEKS = 2  # 未来周数（纯待办）：配合演示时间快进，穿越后每天有任务可打


async def _seed_history(
    session: AsyncSession, user: User, goal: Goal, subjects: list[str], weeks: int
) -> dict[str, Any]:
    today = today_cn()
    this_monday = today - timedelta(days=today.weekday())
    summary: dict[str, Any] = {
        "plans": 0,
        "tasks": 0,
        "done": 0,
        "skipped": 0,
        "todo": 0,
        "life": 0,
        "journals": 0,
    }
    skip_counter: dict[str, int] = {}

    # 从最早一周排到未来周（负 offset）：过去=已结算的故事数据，未来=纯待办
    for week_offset in range(weeks - 1, -_FUTURE_WEEKS - 1, -1):
        week_start = this_monday - timedelta(days=7 * week_offset)
        plan = WeeklyPlan(
            goal_id=goal.id,
            week_start=week_start,
            version=weeks - week_offset,
            status=PlanStatus.SUPERSEDED if week_offset > 0 else PlanStatus.ACTIVE,
        )
        session.add(plan)
        await session.flush()  # 拿 plan.id 供任务外键
        summary["plans"] += 1

        for day_offset in range(7):
            day = week_start + timedelta(days=day_offset)
            is_future = day > today
            slots = _SLOTS if day.weekday() < 5 else _SLOTS[:2]  # 工作日 3 件/周末 2 件
            if day == today:
                slots = slots[:2]  # 今天少一点：1 done + 1 todo 更真实
            for slot_index, (slot_hour, done_rate) in enumerate(slots):
                subject = subjects[(day_offset + slot_index) % len(subjects)]
                if is_future or (day == today and slot_index == 1):
                    status = TaskStatus.TODO  # 未来日期全待办：时间快进后每天有任务可打
                elif random.random() < done_rate:
                    status = TaskStatus.DONE
                else:
                    status = TaskStatus.SKIPPED
                duration = random.choice(_DURATIONS)
                task = Task(
                    weekly_plan_id=plan.id,
                    date=day,
                    title=f"{subject} · 专注 {duration} 分钟",
                    duration_minutes=duration,
                    category_label=subject,
                    status=status,
                )
                if status == TaskStatus.DONE:
                    task.completed_at = _stamp(day, slot_hour)
                    task.actual_minutes = duration
                    summary["done"] += 1
                elif status == TaskStatus.SKIPPED:
                    reason = _weighted_reason()
                    task.skipped_at = _stamp(day, slot_hour)
                    task.skip_reason = reason
                    skip_counter[reason.value] = skip_counter.get(reason.value, 0) + 1
                    summary["skipped"] += 1
                else:
                    summary["todo"] += 1
                session.add(task)
                summary["tasks"] += 1

            if is_future:
                continue  # 生活打卡/复盘只造到今天（未来还没发生）

            # 生活三打卡 + 七成天数有轻复盘
            session.add(
                LifeLog(
                    user_id=user.id,
                    date=day,
                    sleep_hours=round(random.uniform(6.0, 7.5), 1),
                    exercise=day.weekday() in (0, 3),  # 周一/周四运动
                    mood=random.randint(2, 5),
                )
            )
            summary["life"] += 1
            if random.random() < 0.7:
                session.add(
                    DailyJournal(
                        user_id=user.id,
                        date=day,
                        mood=random.randint(3, 4),
                        note=random.choice(_NOTES_POOL),
                    )
                )
                summary["journals"] += 1

    await session.commit()
    summary["skip_reasons"] = skip_counter
    return summary


async def _generate_report(session: AsyncSession, user: User) -> str:
    """为本周生成一次周报（真实 LLM）；失败不回滚数据，只给提示。"""
    try:
        config = await LLMSettingsService(session).resolve(user.id)
        if config is None:
            return "未配置模型密钥：周报跳过（图表/热力图数据已就位）"
        backend = await build_backend_from_byok(config)
        week_start = today_cn() - timedelta(days=today_cn().weekday())
        await ReviewerAgent(session, backend).run_weekly(user.id, week_start)
        await session.commit()
        return "本周周报已生成"
    except (CryptoError, Exception) as exc:
        await session.rollback()
        return f"周报生成失败（{exc}）：数据已就位，确认密钥后重跑即可"


async def main() -> None:
    parser = argparse.ArgumentParser(description="面试演示数据回填")
    parser.add_argument("--user", required=True, help="用户名（演示账号）")
    parser.add_argument("--subjects", default="数学,英语,专业课", help="逗号分隔的科目名")
    parser.add_argument("--weeks", type=int, default=4, help="回填周数（默认 4）")
    parser.add_argument("--clean", action="store_true", help="仅清空该用户历史，不生成")
    args = parser.parse_args()
    subjects = [s.strip() for s in args.subjects.split(",") if s.strip()]

    engine = create_db_engine(get_settings().database_url)
    maker: async_sessionmaker[AsyncSession] = create_session_maker(engine)
    async with maker() as session:
        user, _goal = await _find(session, args.user)
        await _clean(session, user.id)
        await session.commit()
        if args.clean:
            print(f"已清空 {args.user!r} 的全部历史数据（目标与账号保留）")
        else:
            summary = await _seed_history(session, user, _goal, subjects, args.weeks)
            summary["report"] = await _generate_report(session, user)
            print(f"回填完成（{args.weeks} 周）：")
            print(
                f"  计划 {summary['plans']} 个 | 任务 {summary['tasks']} 件"
                f"（完成 {summary['done']} / 跳过 {summary['skipped']} / 待办 {summary['todo']}）"
            )
            print(f"  跳过原因分布: {summary['skip_reasons']}")
            print(f"  生活打卡 {summary['life']} 天 | 轻复盘 {summary['journals']} 天")
            print(f"  {summary['report']}")
            print("  → 打开档案页看热力图/趋势/高效时段，首页看目标卡与通知")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
