"""晚间轻复盘与生活三打卡业务。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import today_cn
from app.repositories.journal import JournalRepository, LifeLogRepository
from app.repositories.plan import TaskRepository
from app.schemas.journal import JournalIn, JournalOut
from app.schemas.life import LifeLogIn, LifeLogOut


class JournalService:
    def __init__(self, session: AsyncSession) -> None:
        self._journals = JournalRepository(session)
        self._tasks = TaskRepository(session)
        self._session = session

    async def get_today(self, user_id: int) -> JournalOut:
        day = today_cn()
        journal = await self._journals.get(user_id, day)
        done, total = await self._tasks.day_summary(user_id, day)
        return JournalOut(
            submitted=journal is not None,
            mood=journal.mood if journal else None,
            note=journal.note if journal else None,
            today_done=done,
            today_total=total,
        )

    async def submit(self, user_id: int, payload: JournalIn) -> JournalOut:
        await self._journals.upsert(user_id, today_cn(), payload.mood, payload.note)
        await self._session.commit()
        return await self.get_today(user_id)


class LifeLogService:
    def __init__(self, session: AsyncSession) -> None:
        self._logs = LifeLogRepository(session)
        self._session = session

    async def upsert(self, user_id: int, payload: LifeLogIn) -> LifeLogOut:
        day = payload.date or today_cn()
        log = await self._logs.upsert(
            user_id, day, payload.sleep_hours, payload.exercise, payload.mood
        )
        await self._session.commit()
        return LifeLogOut.model_validate(log)
