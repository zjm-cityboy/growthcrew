"""档案统计模型（对应手机端「档案」Tab 图表数据）。"""

from datetime import date

from pydantic import BaseModel

from app.domain.enums import SkipReason


class DayPoint(BaseModel):
    """热力图单日：date + 完成/总数（前端按 rate 取色阶）。"""

    date: date
    done: int
    total: int


class HeatmapOut(BaseModel):
    days: list[DayPoint]
    weeks: int


class WeekPoint(BaseModel):
    week_start: date  # 周一
    done: int
    total: int
    rate: float  # 0-100，保留 1 位


class TrendsOut(BaseModel):
    weeks: list[WeekPoint]


class ReasonSlice(BaseModel):
    reason: SkipReason
    count: int
    pct: float  # 0-100，保留 1 位


class SkipReasonsOut(BaseModel):
    items: list[ReasonSlice]
    window_days: int


class HoursOut(BaseModel):
    """24 小时直方图（北京时间）：完成时刻与跳过时刻的分布对比。"""

    completion_hours: list[int]  # 长度 24，下标即小时
    skip_hours: list[int]
    window_days: int
