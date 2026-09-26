"""错题本模型（含间隔复习调度字段）。"""

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Mistake(TimestampMixin, Base):
    __tablename__ = "mistakes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # 可选关联目标（如"软考高级"）；SET NULL：目标删除后错题保留
    goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text)
    wrong_answer: Mapped[str] = mapped_column(Text, default="")
    correct_answer: Mapped[str] = mapped_column(Text, default="")
    explanation: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(200), default="")

    # 间隔复习（简化 SM-2：答对间隔翻倍，答错重置为 1 天）
    next_review_at: Mapped[date] = mapped_column(Date, index=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    interval_days: Mapped[int] = mapped_column(Integer, default=1)
    mastered: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)

    goal = relationship("Goal")
