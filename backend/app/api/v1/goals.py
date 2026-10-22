"""目标路由。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.goal import GoalCreateIn, GoalOut
from app.services.errors import NotFoundError
from app.services.goal import GoalService

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: GoalCreateIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GoalOut:
    return await GoalService(session).create(current_user.id, payload)


@router.get("", response_model=list[GoalOut])
async def list_goals(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[GoalOut]:
    return await GoalService(session).list(current_user.id)


@router.get("/{goal_id}", response_model=GoalOut)
async def get_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GoalOut:
    try:
        return await GoalService(session).get(current_user.id, goal_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标不存在") from exc


@router.post("/{goal_id}/archive", response_model=GoalOut)
async def archive_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GoalOut:
    """归档目标：退出各列表并停排生效计划（软删除，历史保留）。"""
    try:
        return await GoalService(session).archive(current_user.id, goal_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标不存在") from exc
