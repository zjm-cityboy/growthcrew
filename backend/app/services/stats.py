"""统计业务：把仓储的分组计数加工成图表友好的形状（周对齐/百分比/小时分桶）。"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import today_cn
from app.domain.enums import TaskStatus
from app.repositories.stats import StatsRepository
from app.schemas.stats import (
    DayPoint,
    HeatmapOut,
    HoursOut,
    ReasonSlice,
    SkipReasonsOut,
    TrendsOut,
    WeekPoint,
)

_CN_TZ = ZoneInfo("Asia/Shanghai")


def _monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _to_cn_hour(value: datetime) -> int:
    """时间戳转北京时间小时（SQLite 朴素值按 UTC 解释，与写入约定一致）。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(_CN_TZ).hour


class StatsService:
    def __init__(self, session: AsyncSession) -> None:
        self._stats = StatsRepository(session)

    async def heatmap(self, user_id: int, weeks: int) -> HeatmapOut:
        end = today_cn()
        # 从 N 周前的周一开始，保证网格完整（前端按周列渲染）
        start = _monday_of(end) - timedelta(weeks=weeks - 1)
        rows = await self._stats.daily_status_counts(user_id, start, end)
        by_date: dict[date, dict[TaskStatus, int]] = {}
        for day, status, count in rows:
            by_date.setdefault(day, {})[status] = count
        days = [
            DayPoint(
                date=day,
                done=counts.get(TaskStatus.DONE, 0),
                total=sum(counts.values()),
            )
            for day, counts in sorted(by_date.items())
        ]
        return HeatmapOut(days=days, weeks=weeks)

    async def trends(self, user_id: int, weeks: int) -> TrendsOut:
        end = today_cn()
        start = _monday_of(end) - timedelta(weeks=weeks - 1)
        rows = await self._stats.daily_status_counts(user_id, start, end)
        weekly: dict[date, dict[TaskStatus, int]] = {}
        for day, status, count in rows:
            weekly.setdefault(_monday_of(day), {})[status] = (
                weekly.get(_monday_of(day), {}).get(status, 0) + count
            )
        points = [
            WeekPoint(
                week_start=monday,
                done=counts.get(TaskStatus.DONE, 0),
                total=sum(counts.values()),
                rate=round(counts.get(TaskStatus.DONE, 0) / sum(counts.values()) * 100, 1)
                if sum(counts.values())
                else 0.0,
            )
            for monday, counts in sorted(weekly.items())
        ]
        return TrendsOut(weeks=points)

    async def skip_reasons(self, user_id: int, window_days: int) -> SkipReasonsOut:
        since = today_cn() - timedelta(days=window_days)
        rows = await self._stats.skip_reason_counts(user_id, since)
        total = sum(count for _, count in rows)
        items = [
            ReasonSlice(
                reason=reason, count=count, pct=round(count / total * 100, 1) if total else 0.0
            )
            for reason, count in sorted(rows, key=lambda r: r[1], reverse=True)
        ]
        return SkipReasonsOut(items=items, window_days=window_days)

    async def hours(self, user_id: int, window_days: int) -> HoursOut:
        since = today_cn() - timedelta(days=window_days)
        completed, skipped = await self._stats.event_timestamps(user_id, since)
        completion = [0] * 24
        skip = [0] * 24
        for value in completed:
            completion[_to_cn_hour(value)] += 1
        for value in skipped:
            skip[_to_cn_hour(value)] += 1
        return HoursOut(completion_hours=completion, skip_hours=skip, window_days=window_days)
