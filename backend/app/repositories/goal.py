"""目标与里程碑的数据访问。"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import GoalCategory
from app.models.goal import Goal, Milestone


class GoalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: int,
        title: str,
        description: str,
        deadline: date | None,
        weekly_hours: float | None,
        category: GoalCategory,
    ) -> Goal:
        goal = Goal(
            user_id=user_id,
            title=title,
            description=description,
            deadline=deadline,
            weekly_hours=weekly_hours,
            category=category,
        )
        self._session.add(goal)
        await self._session.flush()
        await self._session.refresh(goal)
        return goal

    async def list_for_user(self, user_id: int) -> list[Goal]:
        result = await self._session.execute(
            select(Goal)
            .where(Goal.user_id == user_id)
            .options(selectinload(Goal.milestones))
            .order_by(Goal.id.desc())
        )
        return list(result.scalars().all())

    async def get_for_user(self, goal_id: int, user_id: int) -> Goal | None:
        result = await self._session.execute(
            select(Goal)
            .where(Goal.id == goal_id, Goal.user_id == user_id)
            .options(selectinload(Goal.milestones))
        )
        return result.scalar_one_or_none()


class MilestoneRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_create(self, goal_id: int, items: list[tuple[str, date | None]]) -> None:
        """按传入顺序建里程碑，items 为 (标题, 截止日) 列表。P1.2 教练落库时使用。"""
        for order, (title, due_date) in enumerate(items):
            self._session.add(
                Milestone(goal_id=goal_id, order=order, title=title, due_date=due_date)
            )
        await self._session.flush()
