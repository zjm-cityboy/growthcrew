"""晚间轻复盘模型。"""

from pydantic import BaseModel, Field


class JournalIn(BaseModel):
    """晚间两问：状态分 + 一句话感想（客观数据由 GET 接口自动带出）。"""

    mood: int = Field(ge=1, le=5)
    note: str = Field(default="", max_length=1000)


class JournalOut(BaseModel):
    submitted: bool
    mood: int | None
    note: str | None
    today_done: int
    today_total: int
