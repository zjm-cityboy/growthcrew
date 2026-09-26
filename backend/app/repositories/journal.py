"""晚间复盘与生活打卡的数据访问（均按 用户+日期 定位）。"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import DailyJournal, LifeLog


class JournalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int, day: date) -> DailyJournal | None:
        result = await self._session.execute(
            select(DailyJournal).where(DailyJournal.user_id == user_id, DailyJournal.date == day)
        )
        return result.scalar_one_or_none()

    async def upsert(self, user_id: int, day: date, mood: int, note: str) -> DailyJournal:
        journal = await self.get(user_id, day)
        if journal is None:
            journal = DailyJournal(user_id=user_id, date=day)
            self._session.add(journal)
        journal.mood = mood
        journal.note = note
        try:
            await self._session.flush()
        except IntegrityError:
            # 并发首写撞 (user_id, date) 唯一约束：回滚后按"已存在"走覆盖更新
            await self._session.rollback()
            journal = await self.get(user_id, day)
            if journal is None:
                raise
            journal.mood = mood
            journal.note = note
            await self._session.flush()
        return journal


class LifeLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int, day: date) -> LifeLog | None:
        result = await self._session.execute(
            select(LifeLog).where(LifeLog.user_id == user_id, LifeLog.date == day)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: int,
        day: date,
        sleep_hours: float | None,
        exercise: bool | None,
        mood: int | None,
    ) -> LifeLog:
        """按字段合并：请求里没给的字段保持原值。"""
        log = await self.get(user_id, day)
        if log is None:
            log = LifeLog(user_id=user_id, date=day)
            self._session.add(log)
        self._merge_fields(log, sleep_hours, exercise, mood)
        try:
            await self._session.flush()
        except IntegrityError:
            # 并发首写撞唯一约束：回滚后取并发胜者的行继续合并
            await self._session.rollback()
            log = await self.get(user_id, day)
            if log is None:
                raise
            self._merge_fields(log, sleep_hours, exercise, mood)
            await self._session.flush()
        return log

    @staticmethod
    def _merge_fields(
        log: LifeLog,
        sleep_hours: float | None,
        exercise: bool | None,
        mood: int | None,
    ) -> None:
        if sleep_hours is not None:
            log.sleep_hours = sleep_hours
        if exercise is not None:
            log.exercise = exercise
        if mood is not None:
            log.mood = mood
