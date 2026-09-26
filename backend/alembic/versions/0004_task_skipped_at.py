"""tasks 增加 skipped_at（跳过时刻：卡因×时段洞察的数据源）

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "skipped_at")
