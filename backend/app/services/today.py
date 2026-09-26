"""今日视图聚合：手机端「今日」Tab 一屏所需全部数据（零 LLM，纯 SQL + 组装）。"""

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import today_cn
from app.repositories.journal import JournalRepository, LifeLogRepository
from app.repositories.plan import TaskRepository
from app.schemas.life import LifeLogOut
from app.schemas.task import TaskOut
from app.schemas.today import DaySummaryOut, TodayOut

_STREAK_LOOKBACK_DAYS = 365


class TodayService:
    def __init__(self, session: AsyncSession) -> None:
        self._tasks = TaskRepository(session)
        self._life_logs = LifeLogRepository(session)
        self._journals = JournalRepository(session)

    async def get(self, user_id: int) -> TodayOut:
        day = today_cn()
        yesterday_done, yesterday_total = await self._tasks.day_summary(
            user_id, day - timedelta(days=1)
        )
        tasks = await self._tasks.list_by_date(user_id, day)
        life_log = await self._life_logs.get(user_id, day)
        journal = await self._journals.get(user_id, day)
        streak = await self._streak(user_id, day)
        return TodayOut(
            date=day,
            yesterday=DaySummaryOut(done=yesterday_done, total=yesterday_total),
            tasks=[TaskOut.model_validate(task) for task in tasks],
            life_log=LifeLogOut.model_validate(life_log) if life_log else None,
            journal_submitted=journal is not None,
            streak=streak,
        )

    async def _streak(self, user_id: int, day: date) -> int:
        """连续打卡天数：从今天（或昨天，若今天还没完成任何任务）往回数。"""
        done_dates = set(
            await self._tasks.done_dates(user_id, day - timedelta(days=_STREAK_LOOKBACK_DAYS))
        )
        # 今天还没打卡不打断 streak（清晨看仍是连续的），从昨天起算
        cursor = day if day in done_dates else day - timedelta(days=1)
        streak = 0
        while cursor in done_dates:
            streak += 1
            cursor -= timedelta(days=1)
        return streak
