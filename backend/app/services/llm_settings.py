"""BYOK 设置业务：密钥只进加密库、只在响应里脱敏。"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import CryptoError, decrypt_secret, encrypt_secret, mask_secret
from app.repositories.llm_settings import LLMSettingsRepository
from app.schemas.settings import LLMSettingsIn, LLMSettingsOut
from app.services.errors import LLMSettingsError

# 验证用的哑工具：与教练链路同款"带 tools 的调用形态"——
# 普通的 hi 请求测不出"模型不支持函数调用/供应商对 tools 参数处理不同"这类问题
_VERIFY_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "echo",
        "description": "验证连通性：回显文本",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "要回显的文本"}},
            "required": ["text"],
        },
    },
}


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

    async def verify(self, user_id: int) -> None:
        """用已保存配置按教练链路同款形态（带 tools）发一次最小真实调用。

        通过 = 密钥有效 + 模型存在 + 供应商接受函数调用参数，
        与"实际能不能跑教练"口径一致（普通 hi 请求测不到后两者）。
        """
        from app.agents.llm import (
            LLMCallError,
            NoLLMConfiguredError,
            build_backend_from_byok,
        )

        try:
            config = await self.resolve(user_id)
            if config is None:
                raise LLMSettingsError("请先保存模型配置")
            backend = await build_backend_from_byok(config)
        except NoLLMConfiguredError as exc:
            raise LLMSettingsError("请先保存模型配置") from exc
        except CryptoError as exc:
            raise LLMSettingsError("加密密钥已变更，请重新保存模型配置") from exc
        # 强制调用哑工具并校验返回：部分 OpenAI 兼容网关会静默丢弃 tools 参数
        # 只回纯文本——只验证"请求被接受"会误报可用，教练链路随后必挂
        result = await backend.complete(
            [{"role": "user", "content": "验证连通性，请调用 echo 工具回显 ok"}],
            [_VERIFY_TOOL_SCHEMA],
            forced_tool="echo",
        )
        if not result.tool_calls:
            raise LLMCallError("模型未返回工具调用：该网关可能不支持函数调用")

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

        row = await self._repo.get_by_user(user_id)
        if row is None:
            return None
        return ResolvedLLMConfig(
            base_url=row.base_url,
            api_key=decrypt_secret(row.api_key_encrypted),
            model_name=row.model_name,
        )
