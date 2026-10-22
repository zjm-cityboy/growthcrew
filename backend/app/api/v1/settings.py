"""BYOK 设置路由。"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import LLMCallError
from app.api.deps import get_current_user, get_session
from app.core.ratelimit import verify_limiter
from app.models.user import User
from app.schemas.settings import LLMSettingsIn, LLMSettingsOut
from app.services.errors import LLMSettingsError
from app.services.llm_settings import LLMSettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.put("/llm", response_model=LLMSettingsOut)
async def save_llm_settings(
    payload: LLMSettingsIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LLMSettingsOut:
    return await LLMSettingsService(session).save(current_user.id, payload)


@router.post("/llm/verify")
async def verify_llm_settings(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    """用已保存配置按教练同款形态（带 tools）发一次真实调用。

    与"保存"分离：保存只落库（可能配置无效），验证给出可用性结论；
    通过即代表教练链路的调用形态在该模型上工作。限流：每次验证消耗
    用户自己的真实 LLM 配额（防 token 泄露后被刷余额）。
    """
    if not await verify_limiter.allow(f"verify:user:{current_user.id}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="验证太频繁，请一分钟后再试"
        )
    try:
        await LLMSettingsService(session).verify(current_user.id)
    except LLMSettingsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LLMCallError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/llm", response_model=LLMSettingsOut | None)
async def get_llm_settings(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LLMSettingsOut | None:
    return await LLMSettingsService(session).get_masked(current_user.id)
