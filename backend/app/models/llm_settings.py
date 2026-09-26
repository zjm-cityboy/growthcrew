"""BYOK 模型配置表：密钥列只存 Fernet 加密后的密文。"""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserLLMSettings(TimestampMixin, Base):
    __tablename__ = "user_llm_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_llm_settings_user"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    base_url: Mapped[str] = mapped_column(String(500))
    # Fernet 密文（主密钥来自 GC_JWT_SECRET 之外独立的环境变量，P1.2 接入）
    api_key_encrypted: Mapped[str] = mapped_column(String(1000))
    model_name: Mapped[str] = mapped_column(String(100))
