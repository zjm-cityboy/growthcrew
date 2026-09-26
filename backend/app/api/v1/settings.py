"""BYOK 设置路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.settings import LLMSettingsIn, LLMSettingsOut
from app.services.llm_settings import LLMSettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.put("/llm", response_model=LLMSettingsOut)
async def save_llm_settings(
    payload: LLMSettingsIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LLMSettingsOut:
    return await LLMSettingsService(session).save(current_user.id, payload)


@router.get("/llm", response_model=LLMSettingsOut | None)
async def get_llm_settings(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LLMSettingsOut | None:
    return await LLMSettingsService(session).get_masked(current_user.id)
