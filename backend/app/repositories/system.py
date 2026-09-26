"""系统级数据访问（健康探测）。"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SystemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ping(self) -> bool:
        """数据库连通性探测；任何异常都视为不可用（异常细节留给服务端日志）。"""
        try:
            await self._session.execute(text("SELECT 1"))
        except Exception:
            return False
        return True
