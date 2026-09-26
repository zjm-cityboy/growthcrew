"""错题本业务：录题→LLM 讲解→间隔复习调度。

LLM 只做一次"讲解"调用（题目本身就是完整上下文，不需要 RAG）——这是
ADR-0002"只在需要见机行事处用 Agent"的又一次体现。
间隔复习用简化 SM-2：答对间隔翻倍（1→2→4→8→16→32→掌握），答错重置为 1 天。
"""

import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import (
    AssistantResult,
    LLMBackend,
    LLMCallError,
    NoLLMConfiguredError,
    build_backend_from_byok,
)
from app.core.crypto import CryptoError
from app.core.time import today_cn
from app.repositories.mistake import MistakeRepository
from app.schemas.mistake import MistakeCreateIn, MistakeOut
from app.services.errors import LLMSettingsError, NotFoundError, StateConflictError
from app.services.llm_settings import LLMSettingsService

logger = logging.getLogger(__name__)

_EXPLAIN_SYSTEM_PROMPT = (
    "你是 GrowthCrew 的陪练，帮用户理解一道做错的学习题。"
    "请给出：1）正确答案（如果用户没填）；2）为什么用户的答案错了（核心误区）；"
    "3）一个帮助记忆的思路或口诀。简体中文，正文不超过 300 字。"
)

# 间隔序列：答对后翻倍，5 次正确后标记掌握
_MASTERY_THRESHOLD = 5
_MAX_INTERVAL = 32


class MistakeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._mistakes = MistakeRepository(session)

    async def create(
        self, user_id: int, payload: MistakeCreateIn, backend: LLMBackend | None = None
    ) -> MistakeOut:
        """录题 → LLM 生成讲解 → 落库（明天开始复习）。BYOK 未配置时保存无讲解版本。"""
        # P1 修复：goal_id 归属校验（防越权关联 + PG 外键 500）
        goal_id = payload.goal_id
        if goal_id is not None:
            from app.repositories.goal import GoalRepository

            goal = await GoalRepository(self._session).get_for_user(goal_id, user_id)
            if goal is None:
                raise NotFoundError("目标不存在")

        byok_configured = True
        if backend is None:
            try:
                backend = await self._resolve_backend(user_id)
            except LLMSettingsError:
                backend = None
                byok_configured = False

        explanation = ""
        if backend is not None:
            explanation = await self._explain(backend, payload)

        # P2 修复：区分"未配置模型"与"讲解生成失败"两种降级文案
        if not explanation:
            explanation = (
                "（未配置模型，暂无讲解——配好 BYOK 后可重新录入）"
                if not byok_configured
                else "（讲解生成失败，可稍后重新录入）"
            )

        mistake = await self._mistakes.create(
            user_id=user_id,
            question=payload.question,
            wrong_answer=payload.wrong_answer,
            correct_answer=payload.correct_answer,
            explanation=explanation,
            source=payload.source,
            goal_id=goal_id,
            next_review_at=today_cn() + timedelta(days=1),
        )
        await self._session.commit()
        return MistakeOut.model_validate(mistake)

    async def _explain(self, backend: LLMBackend, payload: MistakeCreateIn) -> str:
        user_content = f"题目：{payload.question}\n"
        if payload.wrong_answer:
            user_content += f"我的答案：{payload.wrong_answer}\n"
        if payload.correct_answer:
            user_content += f"正确答案：{payload.correct_answer}\n"
        if payload.source:
            user_content += f"来源：{payload.source}\n"
        try:
            result: AssistantResult = await backend.complete(
                [
                    {"role": "system", "content": _EXPLAIN_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ]
            )
            return result.content.strip()
        except LLMCallError as exc:
            logger.warning("错题讲解 LLM 失败，保存原始题目（无讲解）: %s", exc)
            return ""

    async def review(self, user_id: int, mistake_id: int, correct: bool) -> MistakeOut:
        """复习：答对间隔翻倍，答错重置。连续答对 5 次标记掌握。"""
        mistake = await self._mistakes.get_for_user(mistake_id, user_id)
        if mistake is None or mistake.user_id != user_id:
            raise NotFoundError("错题不存在")
        if mistake.mastered:
            raise StateConflictError("该题已掌握")

        mistake.review_count += 1
        if correct:
            mistake.interval_days = min(mistake.interval_days * 2, _MAX_INTERVAL)
            if mistake.review_count >= _MASTERY_THRESHOLD:
                mistake.mastered = True
        else:
            mistake.interval_days = 1  # 答错重置
            mistake.review_count = 0  # 连续计数清零

        mistake.next_review_at = today_cn() + timedelta(days=mistake.interval_days)
        await self._session.commit()
        return MistakeOut.model_validate(mistake)

    async def list_active(self, user_id: int) -> list[MistakeOut]:
        return [MistakeOut.model_validate(m) for m in await self._mistakes.list_for_user(user_id)]

    async def list_due(self, user_id: int) -> int:
        """今日到期数（晨推集成用）。"""
        return await self._mistakes.count_due(user_id, today_cn())

    async def get_due_detail(self, user_id: int) -> list[MistakeOut]:
        return [
            MistakeOut.model_validate(m) for m in await self._mistakes.list_due(user_id, today_cn())
        ]

    async def _resolve_backend(self, user_id: int) -> LLMBackend:
        try:
            config = await LLMSettingsService(self._session).resolve(user_id)
            return await build_backend_from_byok(config)
        except NoLLMConfiguredError as exc:
            raise LLMSettingsError("请先在设置中配置模型（BYOK 三件套）") from exc
        except CryptoError as exc:
            raise LLMSettingsError("加密密钥已变更，请重新保存模型配置") from exc
