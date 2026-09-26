"""复盘师业务：周报与周三小结（BYOK 后端注入，异常翻译同教练链路）。"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import LLMBackend, LLMCallError, NoLLMConfiguredError, build_backend_from_byok
from app.agents.reviewer import ReviewerAgent, ReviewerError
from app.core.crypto import CryptoError
from app.repositories.report import WeeklyReportRepository
from app.schemas.report import WeeklyReportOut
from app.services.errors import LLMSettingsError, NotFoundError, ReviewFailedError
from app.services.llm_settings import LLMSettingsService

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._reports = WeeklyReportRepository(session)

    async def generate_weekly(
        self,
        user_id: int,
        backend: LLMBackend | None = None,
    ) -> WeeklyReportOut:
        """生成本周周报（同周重跑覆盖），返回报告。"""
        if backend is None:
            backend = await self._resolve_backend(user_id)
        agent = ReviewerAgent(self._session, backend)
        try:
            outcome = await agent.run_weekly(user_id)
        except (ReviewerError, LLMCallError) as exc:
            logger.exception("周报生成失败 user_id=%s", user_id)
            raise ReviewFailedError(str(exc)) from exc
        await self._session.commit()
        report = await self._reports.get_for_user(outcome["report_id"], user_id)
        if report is None:  # pragma: no cover - 理论不可达
            raise NotFoundError("周报不存在")
        return WeeklyReportOut.model_validate(report)

    async def generate_midweek(self, user_id: int, backend: LLMBackend | None = None) -> str:
        if backend is None:
            backend = await self._resolve_backend(user_id)
        agent = ReviewerAgent(self._session, backend)
        try:
            content = await agent.run_midweek(user_id)
        except (ReviewerError, LLMCallError) as exc:
            logger.exception("周三小结生成失败 user_id=%s", user_id)
            raise ReviewFailedError(str(exc)) from exc
        await self._session.commit()
        return content

    async def list_weekly(self, user_id: int) -> list[WeeklyReportOut]:
        reports = await self._reports.list_for_user(user_id)
        return [WeeklyReportOut.model_validate(r) for r in reports]

    async def get_weekly(self, user_id: int, report_id: int) -> WeeklyReportOut:
        report = await self._reports.get_for_user(report_id, user_id)
        if report is None:
            raise NotFoundError("周报不存在")
        return WeeklyReportOut.model_validate(report)

    async def _resolve_backend(self, user_id: int) -> LLMBackend:
        try:
            config = await LLMSettingsService(self._session).resolve(user_id)
            return await build_backend_from_byok(config)
        except NoLLMConfiguredError as exc:
            raise LLMSettingsError("请先在设置中配置模型（BYOK 三件套）") from exc
        except CryptoError as exc:
            raise LLMSettingsError("加密密钥已变更，请重新保存模型配置") from exc
