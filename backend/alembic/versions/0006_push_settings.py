"""push_settings 用户推送通道配置

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        # bark / pushplus / wecom_webhook
        sa.Column(
            "channel",
            sa.Enum(
                "bark",
                "pushplus",
                "wecom_webhook",
                name="pushchannel",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        # Bark: https://api.day.app/<device_key>
        # PushPlus: https://www.pushplus.plus/send/<token>
        # 企微: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<key>
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_push_settings_user"),
    )
    op.create_index("ix_push_settings_user_id", "push_settings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_push_settings_user_id", table_name="push_settings")
    op.drop_table("push_settings")
