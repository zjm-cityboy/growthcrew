"""用户推送通道配置。"""

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, true
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PushSettings(TimestampMixin, Base):
    __tablename__ = "push_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_push_settings_user"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(
        SAEnum(
            "bark", "pushplus", "wecom_webhook", name="pushchannel", native_enum=False, length=20
        )
    )
    endpoint: Mapped[str] = mapped_column(
        String(500)
    )  # 完整 URL（含 device_key/token/webhook key）
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=true(), default=True)
