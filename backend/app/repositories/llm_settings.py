"""BYOK 模型配置的数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_settings import UserLLMSettings


class LLMSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user(self, user_id: int) -> UserLLMSettings | None:
        result = await self._session.execute(
            select(UserLLMSettings).where(UserLLMSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, user_id: int, base_url: str, api_key_encrypted: str, model_name: str
    ) -> UserLLMSettings:
        row = await self.get_by_user(user_id)
        if row is None:
            row = UserLLMSettings(user_id=user_id)
            self._session.add(row)
        row.base_url = base_url
        row.api_key_encrypted = api_key_encrypted
        row.model_name = model_name
        await self._session.flush()
        return row
