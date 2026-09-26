"""站内通知表（晨间摘要/提案提醒/系统通知）。"""

from sqlalchemy import Boolean, ForeignKey, String, Text, false
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import NotificationType
from app.models.base import Base, TimestampMixin

_SA_ENUM_KWARGS = {"native_enum": False, "values_callable": lambda e: [m.value for m in e]}


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, length=20, **_SA_ENUM_KWARGS)
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    read: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
