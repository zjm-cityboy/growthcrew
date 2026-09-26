"""目标与里程碑表。"""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import GoalCategory, GoalStatus, MilestoneStatus
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    # 仅类型标注用，运行时由 SQLAlchemy 注册表按字符串解析（避免循环导入）
    from app.models.plan import WeeklyPlan


class Goal(TimestampMixin, Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 每周可投入小时（排程容量预算；教练访谈追问的信息落在此列）
    weekly_hours: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    category: Mapped[GoalCategory] = mapped_column(
        SAEnum(
            GoalCategory,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    status: Mapped[GoalStatus] = mapped_column(
        SAEnum(
            GoalStatus, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e]
        ),
        default=GoalStatus.ACTIVE,
    )

    # selectin：序列化 GoalOut 需要读 milestones，异步上下文禁止惰性 IO
    milestones: Mapped[list["Milestone"]] = relationship(
        back_populates="goal",
        cascade="all, delete-orphan",
        order_by="Milestone.order",
        lazy="selectin",
    )
    weekly_plans: Mapped[list["WeeklyPlan"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan"
    )


class Milestone(TimestampMixin, Base):
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    order: Mapped[int] = mapped_column(default=0)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[MilestoneStatus] = mapped_column(
        SAEnum(
            MilestoneStatus,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=MilestoneStatus.PENDING,
    )

    goal: Mapped[Goal] = relationship(back_populates="milestones")
