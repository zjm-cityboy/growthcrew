"""计划导入与提案审批模型。"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.domain.enums import ProposalStatus


class ImportPlanIn(BaseModel):
    goal_id: int
    raw_text: str = Field(min_length=5, max_length=20000)  # 一句话也行："我要3个月拿下软考"
    weekly_hours: float | None = Field(default=None, ge=1, le=80)


class ImportOut(BaseModel):
    status: str  # "questions" | "proposal"
    questions: list[str] = []
    proposal_id: int | None = None
    plan_id: int | None = None
    summary: str = ""


class ProposalTaskOut(BaseModel):
    date: date
    title: str
    duration_minutes: int
    category_label: str


class ProposalOut(BaseModel):
    id: int
    status: ProposalStatus
    summary: str
    tasks: list[ProposalTaskOut]
    week_start: date
    version: int
    created_at: datetime
    decided_at: datetime | None
