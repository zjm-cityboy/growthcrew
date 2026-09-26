"""SQLAlchemy 表模型汇总（Alembic 迁移从这里取元数据）。"""

from app.models.base import Base, TimestampMixin
from app.models.goal import Goal, Milestone
from app.models.journal import DailyJournal, LifeLog
from app.models.llm_settings import UserLLMSettings
from app.models.mistake import Mistake
from app.models.notification import Notification
from app.models.plan import PlanProposal, Task, WeeklyPlan
from app.models.push import PushSettings
from app.models.report import WeeklyReport
from app.models.user import RefreshToken, User

__all__ = [
    "Base",
    "DailyJournal",
    "Goal",
    "LifeLog",
    "Milestone",
    "Mistake",
    "Notification",
    "PlanProposal",
    "PushSettings",
    "RefreshToken",
    "Task",
    "TimestampMixin",
    "User",
    "UserLLMSettings",
    "WeeklyPlan",
    "WeeklyReport",
]
