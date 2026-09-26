"""统计聚合的数据访问：热力图/周趋势/卡因分布/时段直方图的原料查询。

口径与 repositories.plan 一致：只统计 ACTIVE + SUPERSEDED 计划的任务
（草稿/待审批对用户不可见）。跨方言的加工（周对齐、小时分桶）放 service 层，
SQL 只做分组计数——strftime/extract 在 SQLite 与 PG 间不通用。
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.constants import COUNTED_PLAN_STATUSES
from app.domain.enums import SkipReason, TaskStatus
from app.models.goal import Goal
from app.models.plan import Task, WeeklyPlan


def _task_in_scope(user_id: int) -> list[Any]:
    return [
        Task.weekly_plan_id == WeeklyPlan.id,
        WeeklyPlan.goal_id == Goal.id,
        Goal.user_id == user_id,
        WeeklyPlan.status.in_(COUNTED_PLAN_STATUSES),
    ]


class StatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def daily_status_counts(
        self, user_id: int, start: date, end: date
    ) -> list[tuple[date, TaskStatus, int]]:
        """按 (日期, 状态) 分组计数。"""
        stmt = (
            select(Task.date, Task.status, func.count())
            .join(WeeklyPlan, Task.weekly_plan_id == WeeklyPlan.id)
            .join(Goal, WeeklyPlan.goal_id == Goal.id)
            .where(Task.date >= start, Task.date <= end, *_task_in_scope(user_id))
            .group_by(Task.date, Task.status)
        )
        result = await self._session.execute(stmt)
        return [(row[0], row[1], int(row[2])) for row in result.all()]

    async def skip_reason_counts(self, user_id: int, since: date) -> list[tuple[SkipReason, int]]:
        """卡因分布：仅已跳过且有卡因的任务。"""
        stmt = (
            select(Task.skip_reason, func.count())
            .join(WeeklyPlan, Task.weekly_plan_id == WeeklyPlan.id)
            .join(Goal, WeeklyPlan.goal_id == Goal.id)
            .where(
                Task.date >= since,
                Task.status == TaskStatus.SKIPPED,
                Task.skip_reason.is_not(None),
                *_task_in_scope(user_id),
            )
            .group_by(Task.skip_reason)
        )
        result = await self._session.execute(stmt)
        return [(row[0], int(row[1])) for row in result.all()]

    async def event_timestamps(
        self, user_id: int, since: date
    ) -> tuple[list[datetime], list[datetime]]:
        """拉取完成/跳过时刻原始值（小时分桶在 Python 侧做，跨方言安全）。"""
        stmt = (
            select(Task.completed_at, Task.skipped_at)
            .join(WeeklyPlan, Task.weekly_plan_id == WeeklyPlan.id)
            .join(Goal, WeeklyPlan.goal_id == Goal.id)
            .where(
                Task.date >= since,
                or_(Task.completed_at.is_not(None), Task.skipped_at.is_not(None)),
                *_task_in_scope(user_id),
            )
        )
        result = await self._session.execute(stmt)
        rows = result.all()  # Result.all() 只能消费一次：先取回再分别抽取
        completed = [row[0] for row in rows if row[0] is not None]
        skipped = [row[1] for row in rows if row[1] is not None]
        return completed, skipped
