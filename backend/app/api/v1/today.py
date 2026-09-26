"""今日视图聚合路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.today import TodayOut
from app.services.today import TodayService

router = APIRouter(prefix="/today", tags=["today"])


@router.get("", response_model=TodayOut)
async def get_today(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TodayOut:
    return await TodayService(session).get(current_user.id)
