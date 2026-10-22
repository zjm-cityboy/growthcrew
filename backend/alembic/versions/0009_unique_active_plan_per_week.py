"""同目标同周只允许一个生效中计划（部分唯一索引，防并发双批）。

Revision ID: 0009
Revises: 0008
"""

from alembic import op
from sqlalchemy import text

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# 枚举值以中文落库（SAEnum native_enum=False 的 values 模式）
_WHERE = text("status = '生效中'")


def upgrade() -> None:
    # 先清理历史脏数据（若存在同周多个生效），否则唯一索引建不起来
    op.execute(
        """
        DELETE FROM weekly_plans WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY goal_id, week_start
                    ORDER BY CASE WHEN status = '生效中' THEN 0 ELSE 1 END, id DESC
                ) AS rn
                FROM weekly_plans WHERE status = '生效中'
            ) ranked WHERE rn > 1
        )
        """
    )
    op.create_index(
        "uq_weekly_plan_active_per_week",
        "weekly_plans",
        ["goal_id", "week_start"],
        unique=True,
        sqlite_where=_WHERE,
        postgresql_where=_WHERE,
    )


def downgrade() -> None:
    op.drop_index("uq_weekly_plan_active_per_week", table_name="weekly_plans")
