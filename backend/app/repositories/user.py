"""用户与刷新令牌的数据访问。"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import RefreshToken, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[User]:
        """全量用户（定时任务广播用；当前规模小，分页从简）。"""
        result = await self._session.execute(select(User).order_by(User.id))
        return list(result.scalars().all())

    async def create(self, username: str, password_hash: str) -> User:
        user = User(username=username, password_hash=password_hash)
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(token)
        await self._session.flush()

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken) -> None:
        token.revoked = True
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: int) -> int:
        """撤销该用户全部有效刷新令牌（登出用），返回撤销条数。"""
        result = await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
            .values(revoked=True)
        )
        return int(getattr(result, "rowcount", 0))

    async def revoke_by_hash(self, token_hash: str) -> bool:
        """原子撤销：单条 UPDATE 带 revoked=false 条件。

        返回 False 表示该令牌已被撤销（并发重放），调用方应拒绝请求。
        这消除了先 SELECT 再 UPDATE 的竞态窗口。
        """
        result = await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked.is_(False))
            .values(revoked=True)
        )
        # execute(update) 运行时返回带 rowcount 的 CursorResult；mypy 只见 Result 基类
        return bool(int(getattr(result, "rowcount", 0)))
