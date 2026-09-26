"""错题本模型。"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class MistakeCreateIn(BaseModel):
    question: str = Field(min_length=5, max_length=3000)
    wrong_answer: str = Field(default="", max_length=2000)
    correct_answer: str = Field(default="", max_length=2000)  # 留空让 LLM 补
    source: str = Field(default="", max_length=200)
    goal_id: int | None = None


class MistakeReviewIn(BaseModel):
    correct: bool  # True=答对了 / False=又错了


class MistakeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    wrong_answer: str
    correct_answer: str
    explanation: str
    source: str
    next_review_at: date
    review_count: int
    interval_days: int
    mastered: bool
    created_at: datetime


class MistakeDueOut(BaseModel):
    due_count: int
    mistakes: list[MistakeOut]
