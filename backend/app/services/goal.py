"""目标业务：创建与查询。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.goal import GoalRepository
from app.schemas.goal import GoalCreateIn, GoalOut
from app.services.errors import NotFoundError


class GoalService:
    def __init__(self, session: AsyncSession) -> None:
        self._goals = GoalRepository(session)
        self._session = session

    async def create(self, user_id: int, payload: GoalCreateIn) -> GoalOut:
        goal = await self._goals.create(
            user_id=user_id,
            title=payload.title,
            description=payload.description,
            deadline=payload.deadline,
            weekly_hours=payload.weekly_hours,
            category=payload.category,
        )
        await self._session.commit()
        return GoalOut.model_validate(goal)

    async def list(self, user_id: int) -> list[GoalOut]:
        goals = await self._goals.list_for_user(user_id)
        return [GoalOut.model_validate(goal) for goal in goals]

    async def get(self, user_id: int, goal_id: int) -> GoalOut:
        goal = await self._goals.get_for_user(goal_id, user_id)
        if goal is None:
            raise NotFoundError("目标不存在")
        return GoalOut.model_validate(goal)
