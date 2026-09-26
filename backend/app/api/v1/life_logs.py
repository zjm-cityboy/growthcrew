"""生活三打卡路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.life import LifeLogIn, LifeLogOut
from app.services.journal import LifeLogService

router = APIRouter(prefix="/life-logs", tags=["life-logs"])


@router.post("", response_model=LifeLogOut)
async def upsert_life_log(
    payload: LifeLogIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LifeLogOut:
    return await LifeLogService(session).upsert(current_user.id, payload)
