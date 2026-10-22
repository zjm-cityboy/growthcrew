"""通用依赖：数据库会话与当前用户。"""

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import CredentialsError, decode_access_token
from app.models.user import User
from app.services.auth import AuthService

_bearer = HTTPBearer(auto_error=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """每个请求一个会话；引擎/会话工厂挂在 app.state 上（便于测试注入）。"""
    async with request.app.state.session_maker() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = decode_access_token(credentials.credentials, get_settings())
    except CredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user = await AuthService(session, get_settings()).get_active_user(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已停用",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """管理后台守卫：用户名在 GC_ADMIN_USERNAMES 中才放行（部署者自控）。"""
    if current_user.username not in get_settings().admin_usernames:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无管理员权限",
        )
    return current_user
