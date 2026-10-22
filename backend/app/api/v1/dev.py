"""演示专用路由：时间快进（仅 GC_DEMO_MODE=1 时挂载，否则整组 404）。

面试演示用：点一下"+1 天"，今日任务/连续打卡/统计窗口/周报周期整体穿越，
现场展示完整闭环而不用真等一天。覆盖值仅存进程内存，重启即回真实时间。
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.time import demo_clock, set_demo_clock, today_cn
from app.models.user import User

router = APIRouter(prefix="/dev", tags=["dev"])


class ClockOut(BaseModel):
    demo_mode: bool
    today: str  # 当前生效的"今天"（覆盖后即穿越日期）
    override: str | None = None  # 覆盖值；None = 真实时间


class ClockIn(BaseModel):
    date: str | None = Field(default=None, description="目标日期 YYYY-MM-DD")
    advance_days: int = Field(
        default=0,
        ge=-3650,
        le=3650,
        description="从当前快进天数，可负（±10 年内防 timedelta 溢出）",
    )
    reset: bool = Field(default=False, description="回到真实时间")


@router.get("/clock", response_model=ClockOut)
async def get_clock(current_user: User = Depends(get_current_user)) -> ClockOut:
    if not get_settings().demo_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    override = demo_clock()
    return ClockOut(
        demo_mode=True,
        today=today_cn().isoformat(),
        override=override.isoformat() if override else None,
    )


@router.post("/clock", response_model=ClockOut)
async def post_clock(payload: ClockIn, current_user: User = Depends(get_current_user)) -> ClockOut:
    if not get_settings().demo_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if payload.reset:
        set_demo_clock(None)
    elif payload.date:
        try:
            set_demo_clock(date.fromisoformat(payload.date))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="日期格式应为 YYYY-MM-DD"
            ) from exc
    else:
        set_demo_clock(today_cn() + timedelta(days=payload.advance_days))
    override = demo_clock()
    return ClockOut(
        demo_mode=True,
        today=today_cn().isoformat(),
        override=override.isoformat() if override else None,
    )
