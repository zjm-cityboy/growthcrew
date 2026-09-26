"""生活三打卡模型。"""

from datetime import date as _date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LifeLogIn(BaseModel):
    """三项均可选，但至少要有一项；date 缺省为今天（服务端北京时间口径）。

    注意：字段名 date 与类型名冲突，注解统一用字符串引用模块级 _date。
    """

    date: "_date | None" = None
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    exercise: bool | None = None
    mood: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "LifeLogIn":
        if self.sleep_hours is None and self.exercise is None and self.mood is None:
            msg = "至少提供 sleep_hours / exercise / mood 中的一项"
            raise ValueError(msg)
        return self


class LifeLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: "_date"
    sleep_hours: float | None
    exercise: bool
    mood: int | None
