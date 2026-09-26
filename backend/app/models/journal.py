"""晚间轻复盘与生活三打卡表（均按 用户+日期 唯一）。"""

from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DailyJournal(TimestampMixin, Base):
    __tablename__ = "daily_journals"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_journals_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    mood: Mapped[int] = mapped_column(Integer)  # 1-5，schema 层校验
    note: Mapped[str] = mapped_column(String(1000), default="")


class LifeLog(TimestampMixin, Base):
    __tablename__ = "life_logs"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_life_logs_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    # 睡眠时长（小时，1 位小数）；exercise 当日是否运动；心情 1-5
    sleep_hours: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    exercise: Mapped[bool] = mapped_column(Boolean, default=False)
    mood: Mapped[int | None] = mapped_column(Integer, nullable=True)
