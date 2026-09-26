"""周计划 / 任务 / 提案的数据访问。

任务的归属链是 task → weekly_plan → goal → user，
所有按用户取任务的查询都必须带这条 join，防止越权。
"""

from datetime import date

from sqlalchemy import distinct, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.time import today_cn
from app.domain.constants import COUNTED_PLAN_STATUSES
from app.domain.enums import PlanStatus, ProposalStatus, TaskStatus
from app.models.goal import Goal
from app.models.plan import PlanProposal, Task, WeeklyPlan


class WeeklyPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, goal_id: int, week_start: date, status: PlanStatus, version: int
    ) -> WeeklyPlan:
        plan = WeeklyPlan(goal_id=goal_id, week_start=week_start, status=status, version=version)
        self._session.add(plan)
        await self._session.flush()
        await self._session.refresh(plan)
        return plan

    async def next_version(self, goal_id: int, week_start: date) -> int:
        result = await self._session.execute(
            select(func.max(WeeklyPlan.version)).where(
                WeeklyPlan.goal_id == goal_id, WeeklyPlan.week_start == week_start
            )
        )
        current = result.scalar_one_or_none()
        return (current or 0) + 1

    async def supersede_actives(self, goal_id: int, week_start: date, keep_plan_id: int) -> int:
        """把同目标同周的其他生效计划置为已替代（新版本生效时调用），返回受影响行数。"""
        result = await self._session.execute(
            update(WeeklyPlan)
            .where(
                WeeklyPlan.goal_id == goal_id,
                WeeklyPlan.week_start == week_start,
                WeeklyPlan.status == PlanStatus.ACTIVE,
                WeeklyPlan.id != keep_plan_id,
            )
            .values(status=PlanStatus.SUPERSEDED)
        )
        return int(getattr(result, "rowcount", 0))


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def transition_status(
        self,
        task_id: int,
        user_id: int,
        from_status: TaskStatus,
        to_status: TaskStatus,
        **extra_fields: object,
    ) -> Task | None:
        """原子状态迁移：条件 UPDATE 带 from_status 条件，防并发竞态。

        返回更新后的 Task（含归属链校验）；返回 None 表示状态已被并发请求改走。
        extra_fields 支持附带更新 completed_at / skip_reason / skipped_at 等。
        """
        values: dict[str, object] = {"status": to_status}
        values.update(extra_fields)
        result = await self._session.execute(
            update(Task)
            .where(
                Task.id == task_id,
                Task.status == from_status,
                Task.weekly_plan_id == WeeklyPlan.id,
                WeeklyPlan.goal_id == Goal.id,
                Goal.user_id == user_id,
            )
            .values(**values)
        )
        if int(getattr(result, "rowcount", 0)) == 0:
            return None
        # 回读完整对象（含归属校验通过后的最终状态）
        return await self.get_for_user(task_id, user_id)

    async def create(
        self,
        weekly_plan_id: int,
        date: date,
        title: str,
        duration_minutes: int = 30,
        category_label: str = "",
        status: TaskStatus = TaskStatus.TODO,
    ) -> Task:
        task = Task(
            weekly_plan_id=weekly_plan_id,
            date=date,
            title=title,
            duration_minutes=duration_minutes,
            category_label=category_label,
            status=status,
        )
        self._session.add(task)
        await self._session.flush()
        await self._session.refresh(task)
        return task

    async def get_for_user(self, task_id: int, user_id: int) -> Task | None:
        result = await self._session.execute(
            select(Task)
            .join(WeeklyPlan, Task.weekly_plan_id == WeeklyPlan.id)
            .join(Goal, WeeklyPlan.goal_id == Goal.id)
            .where(Task.id == task_id, Goal.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_by_date(
        self, user_id: int, day: date, only_active_plans: bool = True
    ) -> list[Task]:
        conditions = [Task.date == day, Goal.user_id == user_id]
        if only_active_plans:
            conditions.append(WeeklyPlan.status == PlanStatus.ACTIVE)
        stmt = (
            select(Task)
            .join(WeeklyPlan, Task.weekly_plan_id == WeeklyPlan.id)
            .join(Goal, WeeklyPlan.goal_id == Goal.id)
            .where(*conditions)
            .order_by(Task.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def day_summary(self, user_id: int, day: date) -> tuple[int, int]:
        """某日 (done, total)，口径：排除草稿/待审批计划。"""
        stmt = (
            select(Task.status, func.count())
            .join(WeeklyPlan, Task.weekly_plan_id == WeeklyPlan.id)
            .join(Goal, WeeklyPlan.goal_id == Goal.id)
            .where(
                Task.date == day,
                Goal.user_id == user_id,
                WeeklyPlan.status.in_(COUNTED_PLAN_STATUSES),
            )
            .group_by(Task.status)
        )
        result = await self._session.execute(stmt)
        counts: dict[TaskStatus, int] = {}
        for status, count in result.all():
            counts[status] = count
        total = sum(counts.values())
        return counts.get(TaskStatus.DONE, 0), total

    async def done_dates(self, user_id: int, since: date) -> list[date]:
        """自 since 起有已完成任务的日期（streak 计算用，升序）。"""
        stmt = (
            select(distinct(Task.date))
            .join(WeeklyPlan, Task.weekly_plan_id == WeeklyPlan.id)
            .join(Goal, WeeklyPlan.goal_id == Goal.id)
            .where(
                Task.date >= since,
                Task.date <= today_cn(),
                Goal.user_id == user_id,
                Task.status == TaskStatus.DONE,
                WeeklyPlan.status.in_(COUNTED_PLAN_STATUSES),
            )
            .order_by(Task.date)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class PlanProposalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, weekly_plan_id: int, diff: dict[str, object], note: str) -> PlanProposal:
        proposal = PlanProposal(weekly_plan_id=weekly_plan_id, diff=diff, note=note)
        self._session.add(proposal)
        await self._session.flush()
        await self._session.refresh(proposal)
        return proposal

    async def list_for_user(self, user_id: int, limit: int = 20) -> list[PlanProposal]:
        """最近的提案列表（对话/档案页展示）。"""
        result = await self._session.execute(
            select(PlanProposal)
            .join(WeeklyPlan, PlanProposal.weekly_plan_id == WeeklyPlan.id)
            .join(Goal, WeeklyPlan.goal_id == Goal.id)
            .where(Goal.user_id == user_id)
            .options(selectinload(PlanProposal.weekly_plan))
            .order_by(PlanProposal.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_for_user(self, proposal_id: int, user_id: int) -> PlanProposal | None:
        """按归属链 proposal → plan → goal → user 取提案（预载计划防惰性 IO）。"""
        result = await self._session.execute(
            select(PlanProposal)
            .join(WeeklyPlan, PlanProposal.weekly_plan_id == WeeklyPlan.id)
            .join(Goal, WeeklyPlan.goal_id == Goal.id)
            .where(PlanProposal.id == proposal_id, Goal.user_id == user_id)
            .options(selectinload(PlanProposal.weekly_plan))
        )
        return result.scalar_one_or_none()

    async def transition(
        self, proposal_id: int, from_status: ProposalStatus, to_status: ProposalStatus
    ) -> bool:
        """条件状态迁移（PENDING→APPROVED/REJECTED）：单条原子 UPDATE，
        返回 False 表示已被并发请求处理（映射 409 而非双写）。"""
        result = await self._session.execute(
            update(PlanProposal)
            .where(PlanProposal.id == proposal_id, PlanProposal.status == from_status)
            .values(status=to_status, decided_at=func.now())
        )
        return bool(int(getattr(result, "rowcount", 0)))
