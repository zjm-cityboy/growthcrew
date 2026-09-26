"""LLM 后端抽象：OpenAI 兼容实现 + 可注入的测试替身。

真实调用只发生在 OpenAICompatBackend；测试注入 FakeBackend，
保证 CI 零网络、零 token。
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from openai import AsyncOpenAI, OpenAIError

from app.services.llm_settings import ResolvedLLMConfig

# 单次调用超时与重试：Agent 链路在单个 HTTP 请求内串行多次调用，
# 默认 600s 超时会把请求与 DB 连一起拖死
_REQUEST_TIMEOUT_SECONDS = 30.0
_MAX_RETRIES = 1


class NoLLMConfiguredError(Exception):
    """用户尚未配置 BYOK 三件套。"""


class LLMCallError(Exception):
    """上游模型调用失败（网络/限流/供应商错误）。"""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class AssistantResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMBackend(Protocol):
    """Agent 依赖的最小接口：带工具的对话补全。"""

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        forced_tool: str | None = None,
    ) -> AssistantResult:
        """返回助手消息（文本 + 工具调用）。forced_tool 强制模型调用指定工具。"""
        ...


def _parse_tool_calls(raw_calls: list[Any] | None) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for raw in raw_calls or []:
        fn = raw.function
        try:
            args = json.loads(fn.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append(ToolCall(id=raw.id, name=fn.name, arguments=args))
    return calls


class OpenAICompatBackend:
    """OpenAI 兼容实现（硅基流动/DeepSeek/OpenAI 等均适用）。"""

    def __init__(self, config: ResolvedLLMConfig) -> None:
        self._client = AsyncOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            max_retries=_MAX_RETRIES,
        )
        self._model = config.model_name

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        forced_tool: str | None = None,
    ) -> AssistantResult:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            if forced_tool:
                kwargs["tool_choice"] = {"type": "function", "function": {"name": forced_tool}}
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except OpenAIError as exc:
            raise LLMCallError(f"模型调用失败（{exc.__class__.__name__}），请稍后重试") from exc
        message = response.choices[0].message
        return AssistantResult(
            content=message.content or "",
            tool_calls=_parse_tool_calls(message.tool_calls),
        )


async def build_backend_from_byok(
    resolve_config: ResolvedLLMConfig | None,
) -> LLMBackend:
    """按用户 BYOK 配置构建后端；未配置时抛 NoLLMConfiguredError。"""
    if resolve_config is None:
        raise NoLLMConfiguredError
    return OpenAICompatBackend(resolve_config)
