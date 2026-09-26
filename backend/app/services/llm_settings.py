"""BYOK 设置业务：密钥只进加密库、只在响应里脱敏。"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_secret, mask_secret
from app.repositories.llm_settings import LLMSettingsRepository
from app.schemas.settings import LLMSettingsIn, LLMSettingsOut


@dataclass(frozen=True)
class ResolvedLLMConfig:
    """给 Agent 层用的解密后配置（仅存在于内存，不落日志）。"""

    base_url: str
    api_key: str
    model_name: str


class LLMSettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = LLMSettingsRepository(session)
        self._session = session

    async def save(self, user_id: int, payload: LLMSettingsIn) -> LLMSettingsOut:
        row = await self._repo.upsert(
            user_id=user_id,
            base_url=payload.base_url,
            api_key_encrypted=encrypt_secret(payload.api_key),
            model_name=payload.model_name,
        )
        await self._session.commit()
        return LLMSettingsOut(
            base_url=row.base_url,
            model_name=row.model_name,
            api_key_masked=mask_secret(payload.api_key),
        )

    async def get_masked(self, user_id: int) -> LLMSettingsOut | None:
        row = await self._repo.get_by_user(user_id)
        if row is None:
            return None
        # 已存密钥无法还原明文做脱敏 → 展示固定占位（保存时会返回真实脱敏值）
        return LLMSettingsOut(
            base_url=row.base_url,
            model_name=row.model_name,
            api_key_masked="已配置（隐藏）",
        )

    async def resolve(self, user_id: int) -> ResolvedLLMConfig | None:
        """解密用户配置供 Agent 使用；未配置返回 None。"""
        from app.core.crypto import decrypt_secret

        row = await self._repo.get_by_user(user_id)
        if row is None:
            return None
        return ResolvedLLMConfig(
            base_url=row.base_url,
            api_key=decrypt_secret(row.api_key_encrypted),
            model_name=row.model_name,
        )
