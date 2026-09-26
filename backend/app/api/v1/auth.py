"""认证路由。"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.core.config import get_settings
from app.core.ratelimit import login_limiter, register_limiter
from app.models.user import User
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenOut, UserOut
from app.services.auth import (
    AuthService,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    UsernameTakenError,
)

router = APIRouter()

_RETRY_AFTER_SECONDS = "60"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _too_many_requests() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="尝试过于频繁，请稍后再试",
        headers={"Retry-After": _RETRY_AFTER_SECONDS},
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    # 注册要跑 CPU 密集的 argon2 哈希且无需认证，按 IP 紧限额
    if not await register_limiter.allow(f"register:ip:{_client_ip(request)}"):
        raise _too_many_requests()
    service = AuthService(session, get_settings())
    try:
        return await service.register(payload)
    except UsernameTakenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已被注册") from exc


@router.post("/login", response_model=TokenOut)
async def login(
    payload: LoginIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenOut:
    # 双桶限速：IP 桶挡分布式撞库，用户名桶挡单账号定向爆破
    ip_ok = await login_limiter.allow(f"login:ip:{_client_ip(request)}")
    user_ok = await login_limiter.allow(f"login:user:{payload.username}")
    if not (ip_ok and user_ok):
        raise _too_many_requests()
    service = AuthService(session, get_settings())
    try:
        return await service.login(payload)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
        ) from exc


@router.post("/refresh", response_model=TokenOut)
async def refresh(
    payload: RefreshIn,
    session: AsyncSession = Depends(get_session),
) -> TokenOut:
    service = AuthService(session, get_settings())
    try:
        return await service.refresh(payload.refresh_token)
    except InvalidRefreshTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌无效或已过期"
        ) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """登出：服务端撤销全部刷新令牌（前端另行清除本地存储）。"""
    await AuthService(session, get_settings()).logout(current_user.id)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
