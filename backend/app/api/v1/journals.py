"""晚间轻复盘路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.journal import JournalIn, JournalOut
from app.services.journal import JournalService

router = APIRouter(prefix="/journals", tags=["journals"])


@router.get("/today", response_model=JournalOut)
async def get_today_journal(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> JournalOut:
    return await JournalService(session).get_today(current_user.id)


@router.post("/today", response_model=JournalOut)
async def submit_today_journal(
    payload: JournalIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> JournalOut:
    return await JournalService(session).submit(current_user.id, payload)
