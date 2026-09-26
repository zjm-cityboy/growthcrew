"""认证业务：注册 / 登录 / 刷新令牌轮换。

刷新令牌采用旋转策略：每次刷新以原子方式作废旧令牌并签发新对，
并发重放同一令牌时只有一个请求能成功（泄漏可检测）。
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_dummy_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user import RefreshTokenRepository, UserRepository
from app.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut


class UsernameTakenError(Exception):
    """用户名已被注册。"""


class InvalidCredentialsError(Exception):
    """用户名或密码错误（统一模糊提示，不区分哪项错）。"""


class InvalidRefreshTokenError(Exception):
    """刷新令牌无效、已撤销、已过期或已重放。"""


def _as_utc(dt: datetime) -> datetime:
    """SQLite 返回朴素时间，统一补 UTC 再比较。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)
        self._session = session
        self._settings = settings

    async def register(self, payload: RegisterIn) -> UserOut:
        if await self._users.get_by_username(payload.username) is not None:
            raise UsernameTakenError(payload.username)
        try:
            user = await self._users.create(
                username=payload.username,
                password_hash=hash_password(payload.password),
            )
        except IntegrityError as exc:
            # 并发注册同名用户：唯一约束兜底，同样映射为 409
            await self._session.rollback()
            raise UsernameTakenError(payload.username) from exc
        await self._session.commit()
        return UserOut.model_validate(user)

    async def login(self, payload: LoginIn) -> TokenOut:
        user = await self._users.get_by_username(payload.username)
        if user is None:
            verify_dummy_password(payload.password)  # 抹平时延，防账号枚举
            raise InvalidCredentialsError(payload.username)
        if not verify_password(payload.password, user.password_hash):
            raise InvalidCredentialsError(payload.username)
        return await self._issue_tokens(user)

    async def refresh(self, refresh_token: str) -> TokenOut:
        token = await self._tokens.get_by_hash(hash_refresh_token(refresh_token))
        if token is None or token.revoked or _as_utc(token.expires_at) < datetime.now(UTC):
            raise InvalidRefreshTokenError
        user = await self._users.get(token.user_id)
        if user is None or not user.is_active:
            raise InvalidRefreshTokenError
        # 原子撤销：并发重放时只有一个请求能翻转该行
        if not await self._tokens.revoke_by_hash(token.token_hash):
            raise InvalidRefreshTokenError
        return await self._issue_tokens(user)

    async def logout(self, user_id: int) -> int:
        """登出：撤销该用户全部刷新令牌（服务端吊销，ADR-0004 债务清偿）。"""
        revoked = await self._tokens.revoke_all_for_user(user_id)
        await self._session.commit()
        return revoked

    async def get_active_user(self, user_id: int) -> User | None:
        """按 access token 中的用户 id 取有效用户（供依赖注入使用）。"""
        user = await self._users.get(user_id)
        if user is None or not user.is_active:
            return None
        return user

    async def _issue_tokens(self, user: User) -> TokenOut:
        access = create_access_token(user.id, self._settings)
        raw_refresh, token_hash = generate_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=self._settings.refresh_token_expire_days)
        await self._tokens.create(user.id, token_hash, expires_at)
        await self._session.commit()
        return TokenOut(access_token=access, refresh_token=raw_refresh)
