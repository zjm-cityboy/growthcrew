"""错题本数据访问。"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mistake import Mistake


class MistakeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: int, **fields: object) -> Mistake:
        mistake = Mistake(user_id=user_id, **fields)
        self._session.add(mistake)
        await self._session.flush()
        await self._session.refresh(mistake)
        return mistake

    async def get_for_user(self, mistake_id: int, user_id: int) -> Mistake | None:
        """按 id + user_id 双条件查（防越权）。"""
        from sqlalchemy import select

        result = await self._session.execute(
            select(Mistake).where(Mistake.id == mistake_id, Mistake.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: int, limit: int = 50) -> list[Mistake]:
        result = await self._session.execute(
            select(Mistake)
            .where(Mistake.user_id == user_id, Mistake.mastered.is_(False))
            .order_by(Mistake.next_review_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_due(self, user_id: int, day: date) -> list[Mistake]:
        """今日到期的错题（含逾期）。"""
        result = await self._session.execute(
            select(Mistake)
            .where(
                Mistake.user_id == user_id,
                Mistake.mastered.is_(False),
                Mistake.next_review_at <= day,
            )
            .order_by(Mistake.next_review_at)
            .limit(20)
        )
        return list(result.scalars().all())

    async def count_due(self, user_id: int, day: date) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Mistake)
            .where(
                Mistake.user_id == user_id,
                Mistake.mastered.is_(False),
                Mistake.next_review_at <= day,
            )
        )
        return result.scalar_one() or 0
