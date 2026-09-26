"""mistakes 错题本（含间隔复习调度）

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mistakes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "goal_id", sa.Integer(), sa.ForeignKey("goals.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("wrong_answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("correct_answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=200), nullable=False, server_default=""),
        # 间隔复习：下次复习时间 + 已复习次数 + 间隔天数
        sa.Column("next_review_at", sa.Date(), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("mastered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mistakes_user_id", "mistakes", ["user_id"])
    op.create_index("ix_mistakes_next_review_at", "mistakes", ["next_review_at"])


def downgrade() -> None:
    op.drop_index("ix_mistakes_next_review_at", table_name="mistakes")
    op.drop_index("ix_mistakes_user_id", table_name="mistakes")
    op.drop_table("mistakes")
