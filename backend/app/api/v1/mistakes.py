"""错题本路由。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.mistake import MistakeCreateIn, MistakeDueOut, MistakeOut, MistakeReviewIn
from app.services.errors import NotFoundError, StateConflictError
from app.services.mistake import MistakeService

router = APIRouter(prefix="/mistakes", tags=["mistakes"])


@router.post("", response_model=MistakeOut, status_code=status.HTTP_201_CREATED)
async def create_mistake(
    payload: MistakeCreateIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MistakeOut:
    """录题（BYOK 未配置时仍保存，只是没有讲解）。"""
    return await MistakeService(session).create(current_user.id, payload)


@router.get("", response_model=list[MistakeOut])
async def list_mistakes(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MistakeOut]:
    return await MistakeService(session).list_active(current_user.id)


@router.get("/due", response_model=MistakeDueOut)
async def get_due_mistakes(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MistakeDueOut:
    """今日到期的错题（复习入口）。due_count 与晨推同口径（count_due 无上限）。"""
    service = MistakeService(session)
    mistakes = await service.get_due_detail(current_user.id)
    due_count = await service.list_due(current_user.id)  # count_due（与晨推一致）
    return MistakeDueOut(due_count=due_count, mistakes=mistakes)


@router.post("/{mistake_id}/review", response_model=MistakeOut)
async def review_mistake(
    mistake_id: int,
    payload: MistakeReviewIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MistakeOut:
    try:
        return await MistakeService(session).review(current_user.id, mistake_id, payload.correct)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="错题不存在") from exc
    except StateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
