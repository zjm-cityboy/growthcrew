"""今日视图聚合模型（对应手机端「今日」Tab 一屏所需全部数据）。"""

from datetime import date as _date

from pydantic import BaseModel

from app.schemas.life import LifeLogOut
from app.schemas.task import TaskOut


class DaySummaryOut(BaseModel):
    done: int
    total: int


class TodayOut(BaseModel):
    date: "_date"
    yesterday: DaySummaryOut
    tasks: list[TaskOut]
    life_log: LifeLogOut | None
    journal_submitted: bool
    streak: int
