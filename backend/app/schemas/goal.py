"""目标相关模型。"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import GoalCategory, GoalStatus, MilestoneStatus


class GoalCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    deadline: date | None = None
    weekly_hours: float | None = Field(default=None, ge=1, le=80)
    category: GoalCategory


class MilestoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    order: int
    due_date: date | None
    status: MilestoneStatus


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    deadline: date | None
    weekly_hours: float | None
    category: GoalCategory
    status: GoalStatus
    created_at: datetime
    milestones: list[MilestoneOut] = []
