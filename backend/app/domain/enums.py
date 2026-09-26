"""业务枚举：单一事实来源，models 与 schemas 都从这里导入。"""

from enum import StrEnum


class GoalCategory(StrEnum):
    """目标模板三类：备考 / 项目 / 习惯（对应场景矩阵）。"""

    EXAM = "备考"
    PROJECT = "项目"
    HABIT = "习惯"


class GoalStatus(StrEnum):
    ACTIVE = "进行中"
    ARCHIVED = "已归档"
    DONE = "已完成"


class MilestoneStatus(StrEnum):
    PENDING = "待开始"
    IN_PROGRESS = "进行中"
    DONE = "已完成"


class PlanStatus(StrEnum):
    DRAFT = "草稿"
    PENDING_APPROVAL = "待审批"
    ACTIVE = "生效中"
    SUPERSEDED = "已替代"


class TaskStatus(StrEnum):
    TODO = "todo"
    DONE = "done"
    SKIPPED = "skipped"


class SkipReason(StrEnum):
    """跳过任务的四个卡因：周报洞察的核心数据源。"""

    DISTRACTED = "分心"
    TOO_HARD = "太难"
    TIRED = "疲劳"
    INTERRUPTED = "被打断"


class ProposalStatus(StrEnum):
    PENDING = "待审批"
    APPROVED = "已同意"
    REJECTED = "已拒绝"


class NotificationType(StrEnum):
    MORNING_BRIEF = "晨间摘要"
    EVENING_REMINDER = "晚间提醒"
    MIDWEEK_BRIEF = "周三小结"
    WEEKLY_REPORT = "周报"
    PROPOSAL = "提案待审批"
    SYSTEM = "系统通知"
