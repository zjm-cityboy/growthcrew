"""推送设置路由。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.repositories.push import PushSettingsRepository
from app.schemas.push import PushSettingsIn, PushSettingsOut, PushTestOut
from app.services.push import send_push, validate_push_config

router = APIRouter(prefix="/settings/push", tags=["settings"])


@router.get("", response_model=PushSettingsOut | None)
async def get_push_settings(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PushSettingsOut | None:
    row = await PushSettingsRepository(session).get_by_user(current_user.id)
    return PushSettingsOut.model_validate(row) if row else None


@router.put("", response_model=PushSettingsOut)
async def save_push_settings(
    payload: PushSettingsIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PushSettingsOut:
    error = validate_push_config(payload.channel, payload.endpoint)
    if error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error)
    row = await PushSettingsRepository(session).upsert(
        current_user.id, payload.channel, payload.endpoint, payload.enabled
    )
    await session.commit()
    return PushSettingsOut.model_validate(row)


@router.post("/test", response_model=PushTestOut)
async def test_push(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PushTestOut:
    """发一条测试消息验证通道连通性。"""
    row = await PushSettingsRepository(session).get_by_user(current_user.id)
    if row is None or not row.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="请先配置并启用推送通道"
        )
    delivered = await send_push(
        row.channel, row.endpoint, "GrowthCrew 测试", "如果你看到这条消息，推送通道已就绪 ✅"
    )
    return PushTestOut(delivered=delivered, message="送达" if delivered else "发送失败，请检查端点")
