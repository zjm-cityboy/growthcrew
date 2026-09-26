"""推送配置的数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.push import PushSettings


class PushSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user(self, user_id: int) -> PushSettings | None:
        result = await self._session.execute(
            select(PushSettings).where(PushSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, user_id: int, channel: str, endpoint: str, enabled: bool
    ) -> PushSettings:
        row = await self.get_by_user(user_id)
        if row is None:
            row = PushSettings(user_id=user_id)
            self._session.add(row)
        row.channel = channel
        row.endpoint = endpoint
        row.enabled = enabled
        await self._session.flush()
        return row
