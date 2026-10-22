"""plan_proposals 增加 rejection_reason（拒绝原因：教练下轮自适应的依据）。

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plan_proposals", sa.Column("rejection_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("plan_proposals", "rejection_reason")
