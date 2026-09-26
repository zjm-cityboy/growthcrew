"""周计划、任务与计划提案（HITL 审计）表。"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import PlanStatus, ProposalStatus, SkipReason, TaskStatus
from app.models.base import Base, TimestampMixin
from app.models.goal import Goal

_SA_ENUM_KWARGS = {"native_enum": False, "values_callable": lambda e: [m.value for m in e]}


class WeeklyPlan(TimestampMixin, Base):
    __tablename__ = "weekly_plans"
    __table_args__ = (
        UniqueConstraint("goal_id", "week_start", "version", name="uq_weekly_plans_goal_week_ver"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    # 版本号：计划可回滚的依据，同一 goal 同一周从 v1 递增
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[PlanStatus] = mapped_column(
        SAEnum(PlanStatus, length=20, **_SA_ENUM_KWARGS), default=PlanStatus.DRAFT
    )

    goal: Mapped[Goal] = relationship(back_populates="weekly_plans")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="weekly_plan", cascade="all, delete-orphan"
    )
    proposals: Mapped[list["PlanProposal"]] = relationship(
        back_populates="weekly_plan", cascade="all, delete-orphan"
    )


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    weekly_plan_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_plans.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(String(200))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    # 科目标签（如「数学」「专业课」），计划对齐时生成
    category_label: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, length=20, **_SA_ENUM_KWARGS), default=TaskStatus.TODO
    )
    skip_reason: Mapped[SkipReason | None] = mapped_column(
        SAEnum(SkipReason, length=20, **_SA_ENUM_KWARGS), nullable=True
    )
    actual_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 跳过时刻（卡因×时段洞察的数据源，如"22 点后跳过占八成"）
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    weekly_plan: Mapped[WeeklyPlan] = relationship(back_populates="tasks")


class PlanProposal(TimestampMixin, Base):
    """教练提案的审计记录：谁在何时改了什么、用户批没批（diff 为 JSON 快照）。"""

    __tablename__ = "plan_proposals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    weekly_plan_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_plans.id", ondelete="CASCADE"), index=True
    )
    diff: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ProposalStatus] = mapped_column(
        SAEnum(ProposalStatus, length=20, **_SA_ENUM_KWARGS), default=ProposalStatus.PENDING
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    weekly_plan: Mapped[WeeklyPlan] = relationship(back_populates="proposals")
