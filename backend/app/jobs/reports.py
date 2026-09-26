"""复盘师定时任务：周日 20:00 周报 / 周三 20:00 周三小结。

健壮性约定与晨推一致：当日去重（周报按同周已存在跳过、小结按通知类型去重）
+ 单点隔离（单用户失败只记日志回滚本人）。LLM 失败的用户跳过当日生成，
不影响其他人（这是与晨推不同的点：LLM 可能失败，失败要隔离）。
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.llm import LLMBackend, LLMCallError, build_backend_from_byok
from app.agents.reviewer import ReviewerAgent, ReviewerError
from app.core.crypto import CryptoError
from app.core.time import cn_day_start_utc_naive, today_cn
from app.domain.enums import NotificationType
from app.repositories.notification import NotificationRepository
from app.repositories.report import WeeklyReportRepository
from app.repositories.user import UserRepository
from app.services.llm_settings import LLMSettingsService
from app.services.stats import _monday_of

logger = logging.getLogger(__name__)


async def _resolve_backend(session: AsyncSession, user_id: int) -> LLMBackend | None:
    """BYOK 未配置或密钥失效的用户静默跳过（返回 None），不视为失败。"""
    try:
        config = await LLMSettingsService(session).resolve(user_id)
    except CryptoError:
        return None  # 密钥轮换后旧密文解不开：跳过并等用户重存，不算任务失败
    if config is None:
        return None
    return await build_backend_from_byok(config)


async def weekly_report_job(session_maker: async_sessionmaker[AsyncSession]) -> int:
    """周日 20:00：为已配置 BYOK 的用户生成周报（本周已有则跳过）。"""
    created = 0
    failed = 0
    skipped = 0
    week_start = _monday_of(today_cn())
    async with session_maker() as session:
        users = await UserRepository(session).list_all()
        reports = WeeklyReportRepository(session)
        for user in users:
            try:
                if await reports.get_for_user_by_week(user.id, week_start) is not None:
                    skipped += 1  # 本周已有（手动生成过）→ 跳过
                    continue
                backend = await _resolve_backend(session, user.id)
                if backend is None:
                    skipped += 1
                    continue
                agent = ReviewerAgent(session, backend)
                await agent.run_weekly(user.id, week_start)
                await session.commit()
                created += 1
            except (ReviewerError, LLMCallError) as exc:
                await session.rollback()
                failed += 1
                logger.warning("周报生成失败（业务级）user_id=%s: %s", user.id, exc)
            except Exception:
                await session.rollback()
                failed += 1
                logger.exception("周报任务异常 user_id=%s", user.id)
    logger.info("weekly_report done created=%d failed=%d skipped=%d", created, failed, skipped)
    return created


async def midweek_brief_job(session_maker: async_sessionmaker[AsyncSession]) -> int:
    """周三 20:00：为已配置 BYOK 且当日未发过小结的用户生成周三小结。"""
    created = 0
    failed = 0
    skipped = 0
    async with session_maker() as session:
        users = await UserRepository(session).list_all()
        notifications = NotificationRepository(session)
        since = cn_day_start_utc_naive(today_cn())
        for user in users:
            try:
                if await notifications.exists_since(user.id, NotificationType.MIDWEEK_BRIEF, since):
                    skipped += 1
                    continue
                backend = await _resolve_backend(session, user.id)
                if backend is None:
                    skipped += 1
                    continue
                agent = ReviewerAgent(session, backend)
                await agent.run_midweek(user.id)
                await session.commit()
                created += 1
            except (ReviewerError, LLMCallError) as exc:
                await session.rollback()
                failed += 1
                logger.warning("周三小结生成失败（业务级）user_id=%s: %s", user.id, exc)
            except Exception:
                await session.rollback()
                failed += 1
                logger.exception("周三小结任务异常 user_id=%s", user.id)
    logger.info("midweek_brief done created=%d failed=%d skipped=%d", created, failed, skipped)
    return created
