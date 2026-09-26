"""P1 核心表：goals / milestones / weekly_plans / tasks / plan_proposals / daily_journals / life_logs / notifications / user_llm_settings

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# 字符串枚举（非原生 VARCHAR 枚举）：长度必须与 ORM 侧 length=20 一致，
# 否则迁移建的列比 ORM 声明短，未来加长枚举值时 PG 写入报错而 SQLite 测不出
_ENUM_KW = {"native_enum": False, "length": 20}


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column(
            "category",
            sa.Enum("备考", "项目", "习惯", name="goalcategory", **_ENUM_KW),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("进行中", "已归档", "已完成", name="goalstatus", **_ENUM_KW),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_goals_user_id", "goals", ["user_id"])

    op.create_table(
        "milestones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "goal_id", sa.Integer(), sa.ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("待开始", "进行中", "已完成", name="milestonestatus", **_ENUM_KW),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_milestones_goal_id", "milestones", ["goal_id"])

    op.create_table(
        "weekly_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "goal_id", sa.Integer(), sa.ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status",
            sa.Enum("草稿", "待审批", "生效中", "已替代", name="planstatus", **_ENUM_KW),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "goal_id", "week_start", "version", name="uq_weekly_plans_goal_week_ver"
        ),
    )
    op.create_index("ix_weekly_plans_goal_id", "weekly_plans", ["goal_id"])
    op.create_index("ix_weekly_plans_week_start", "weekly_plans", ["week_start"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "weekly_plan_id",
            sa.Integer(),
            sa.ForeignKey("weekly_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("category_label", sa.String(length=50), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.Enum("todo", "done", "skipped", name="taskstatus", **_ENUM_KW),
            nullable=False,
        ),
        sa.Column(
            "skip_reason",
            sa.Enum("分心", "太难", "疲劳", "被打断", name="skipreason", **_ENUM_KW),
            nullable=True,
        ),
        sa.Column("actual_minutes", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_weekly_plan_id", "tasks", ["weekly_plan_id"])
    op.create_index("ix_tasks_date", "tasks", ["date"])

    op.create_table(
        "plan_proposals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "weekly_plan_id",
            sa.Integer(),
            sa.ForeignKey("weekly_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("diff", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.Enum("待审批", "已同意", "已拒绝", name="proposalstatus", **_ENUM_KW),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_proposals_weekly_plan_id", "plan_proposals", ["weekly_plan_id"])

    op.create_table(
        "daily_journals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("mood", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", name="uq_journals_user_date"),
    )
    op.create_index("ix_daily_journals_user_id", "daily_journals", ["user_id"])

    op.create_table(
        "life_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("sleep_hours", sa.Numeric(3, 1), nullable=True),
        sa.Column("exercise", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mood", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", name="uq_life_logs_user_date"),
    )
    op.create_index("ix_life_logs_user_id", "life_logs", ["user_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "type",
            sa.Enum("晨间摘要", "提案待审批", "系统通知", name="notificationtype", **_ENUM_KW),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    op.create_table(
        "user_llm_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("api_key_encrypted", sa.String(length=1000), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_llm_settings_user"),
    )
    op.create_index("ix_user_llm_settings_user_id", "user_llm_settings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_llm_settings_user_id", table_name="user_llm_settings")
    op.drop_table("user_llm_settings")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_life_logs_user_id", table_name="life_logs")
    op.drop_table("life_logs")
    op.drop_index("ix_daily_journals_user_id", table_name="daily_journals")
    op.drop_table("daily_journals")
    op.drop_index("ix_plan_proposals_weekly_plan_id", table_name="plan_proposals")
    op.drop_table("plan_proposals")
    op.drop_index("ix_tasks_date", table_name="tasks")
    op.drop_index("ix_tasks_weekly_plan_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_weekly_plans_week_start", table_name="weekly_plans")
    op.drop_index("ix_weekly_plans_goal_id", table_name="weekly_plans")
    op.drop_table("weekly_plans")
    op.drop_index("ix_milestones_goal_id", table_name="milestones")
    op.drop_table("milestones")
    op.drop_index("ix_goals_user_id", table_name="goals")
    op.drop_table("goals")
