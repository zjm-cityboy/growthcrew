"""任务相关模型。"""

from datetime import date as _date
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import SkipReason, TaskStatus


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: "_date"
    title: str
    duration_minutes: int
    category_label: str
    status: TaskStatus
    skip_reason: SkipReason | None
    actual_minutes: int | None
    completed_at: datetime | None
    # 教练提示：本周同因跳过≥3 次时出现（承诺的调整在下次生成计划时真实发生）
    coach_hint: str = ""


class TaskCompleteIn(BaseModel):
    actual_minutes: int | None = Field(default=None, ge=0, le=1440)


class TaskSkipIn(BaseModel):
    reason: SkipReason
