"""计划导入对齐与提案审批业务（HITL 在这一层落地，见 ADR-0003）。

Agent 层异常在本层翻译为 services 层错误类型，
API 层只认识 services 的异常（分层铁律：api → service → repository/agents）。
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import LLMBackend, LLMCallError, NoLLMConfiguredError, build_backend_from_byok
from app.agents.planner import PlannerAgent, PlannerError, ProgressReporter
from app.core.crypto import CryptoError
from app.domain.enums import NotificationType, PlanStatus, ProposalStatus
from app.models.plan import PlanProposal
from app.repositories.goal import GoalRepository
from app.repositories.notification import NotificationRepository
from app.repositories.plan import PlanProposalRepository, WeeklyPlanRepository
from app.schemas.proposal import ImportOut, ImportPlanIn, ProposalOut, ProposalTaskOut
from app.services.errors import (
    LLMSettingsError,
    NotFoundError,
    PlannerFailedError,
    StateConflictError,
)
from app.services.llm_settings import LLMSettingsService

logger = logging.getLogger(__name__)


class PlanImportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._goals = GoalRepository(session)
        self._plans = WeeklyPlanRepository(session)
        self._proposals = PlanProposalRepository(session)
        self._notifications = NotificationRepository(session)

    async def start(
        self,
        user_id: int,
        payload: ImportPlanIn,
        backend: LLMBackend | None = None,
        on_event: ProgressReporter | None = None,
    ) -> ImportOut:
        """贴入参考计划 → 教练 Agent 对齐 → 草稿计划 + 待审批提案。

        on_event：可选过程事件接收器（SSE 流式端点用它实时推送教练进度）。
        """
        goal = await self._goals.get_for_user(payload.goal_id, user_id)
        if goal is None:
            raise NotFoundError("目标不存在")
        if backend is None:
            try:
                config = await LLMSettingsService(self._session).resolve(user_id)
                backend = await build_backend_from_byok(config)
            except NoLLMConfiguredError as exc:
                raise LLMSettingsError("请先在设置中配置模型（BYOK 三件套）") from exc
            except CryptoError as exc:
                raise LLMSettingsError("加密密钥已变更，请重新保存模型配置") from exc
        agent = PlannerAgent(self._session, backend, goal, on_event=on_event)
        try:
            outcome = await agent.run(payload.raw_text, payload.weekly_hours)
        except (PlannerError, LLMCallError) as exc:
            logger.exception("计划导入失败（goal_id=%s）", payload.goal_id)
            raise PlannerFailedError(str(exc)) from exc
        if payload.weekly_hours is not None and goal.weekly_hours is None:
            goal.weekly_hours = payload.weekly_hours  # 首次访谈结果落到目标上
        if goal.deadline is None and outcome.parsed_deadline is not None:
            # 用户没手选截止日期 → 回填从文本推导的（"3个月拿下"→ 今天+3个月）
            goal.deadline = outcome.parsed_deadline
        await self._session.commit()
        if outcome.proposal_id is None:
            return ImportOut(status="questions", questions=outcome.questions)
        return ImportOut(
            status="proposal",
            proposal_id=outcome.proposal_id,
            plan_id=outcome.plan_id,
            summary=outcome.summary,
        )

    async def get_proposal(self, user_id: int, proposal_id: int) -> ProposalOut:
        proposal = await self._proposals.get_for_user(proposal_id, user_id)
        if proposal is None:
            raise NotFoundError("提案不存在")
        return self._to_out(proposal)

    async def list_proposals(self, user_id: int) -> list[ProposalOut]:
        return [self._to_out(p) for p in await self._proposals.list_for_user(user_id)]

    async def approve(self, user_id: int, proposal_id: int) -> ProposalOut:
        """批准提案：计划生效、同周旧版替代、发通知。

        PENDING→APPROVED 用条件更新原子完成，并发双批准只有一个成功。
        """
        proposal = await self._proposals.get_for_user(proposal_id, user_id)
        if proposal is None:
            raise NotFoundError("提案不存在")
        plan = proposal.weekly_plan
        if plan.status != PlanStatus.DRAFT:
            raise StateConflictError("该提案关联的计划不在草稿态")
        if not await self._proposals.transition(
            proposal.id, ProposalStatus.PENDING, ProposalStatus.APPROVED
        ):
            raise StateConflictError("该提案已被处理")
        proposal.status = ProposalStatus.APPROVED
        proposal.decided_at = datetime.now(UTC)
        await self._plans.supersede_actives(plan.goal_id, plan.week_start, plan.id)
        plan.status = PlanStatus.ACTIVE
        summary = str(proposal.diff.get("summary", "新周计划"))
        await self._notifications.create(
            user_id=user_id,
            type=NotificationType.SYSTEM,
            title="新计划已生效",
            body=summary,
        )
        await self._session.commit()
        return self._to_out(proposal)

    async def reject(
        self, user_id: int, proposal_id: int, reason: str | None = None
    ) -> ProposalOut:
        proposal = await self._proposals.get_for_user(proposal_id, user_id)
        if proposal is None:
            raise NotFoundError("提案不存在")
        if not await self._proposals.transition(
            proposal.id, ProposalStatus.PENDING, ProposalStatus.REJECTED
        ):
            raise StateConflictError("该提案已被处理")
        proposal.status = ProposalStatus.REJECTED
        proposal.decided_at = datetime.now(UTC)
        # 拒绝原因落库：教练下次排程读取并对应调整（反馈闭环的入口）
        proposal.rejection_reason = (reason or "").strip() or None
        await self._session.commit()
        return self._to_out(proposal)

    # ---------- 管理端代操作：按提案 id 反查归属用户后走同一条审批路径 ----------

    async def _owner_of(self, proposal_id: int) -> int | None:
        from sqlalchemy import select

        from app.models.goal import Goal as GoalModel
        from app.models.plan import PlanProposal as PlanProposalModel
        from app.models.plan import WeeklyPlan as WeeklyPlanModel

        row = (
            await self._session.execute(
                select(GoalModel.user_id)
                .join(WeeklyPlanModel, WeeklyPlanModel.goal_id == GoalModel.id)
                .join(PlanProposalModel, PlanProposalModel.weekly_plan_id == WeeklyPlanModel.id)
                .where(PlanProposalModel.id == proposal_id)
            )
        ).scalar_one_or_none()
        return row

    async def approve_by_admin(self, proposal_id: int) -> ProposalOut:
        owner = await self._owner_of(proposal_id)
        if owner is None:
            raise NotFoundError("提案不存在")
        return await self.approve(owner, proposal_id)

    async def reject_by_admin(self, proposal_id: int, reason: str) -> ProposalOut:
        owner = await self._owner_of(proposal_id)
        if owner is None:
            raise NotFoundError("提案不存在")
        return await self.reject(owner, proposal_id, reason)

    @staticmethod
    def _to_out(proposal: PlanProposal) -> ProposalOut:
        diff = proposal.diff or {}
        tasks = [
            ProposalTaskOut(
                date=task["date"],
                title=str(task.get("title", "")),
                duration_minutes=int(task.get("duration_minutes", 30)),
                category_label=str(task.get("category_label", "")),
            )
            for task in diff.get("tasks", [])
        ]
        return ProposalOut(
            id=proposal.id,
            status=proposal.status,
            summary=str(diff.get("summary", proposal.note)),
            tasks=tasks,
            week_start=proposal.weekly_plan.week_start,
            version=proposal.weekly_plan.version,
            created_at=proposal.created_at,
            decided_at=proposal.decided_at,
        )
