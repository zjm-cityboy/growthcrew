"""周报模型。"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WeeklyReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    week_start: date
    title: str
    content: str
    data_snapshot: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class MidweekOut(BaseModel):
    content: str
