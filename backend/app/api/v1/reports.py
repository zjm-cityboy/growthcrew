"""复盘师路由：周报与周三小结。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.report import MidweekOut, WeeklyReportOut
from app.services.errors import LLMSettingsError, NotFoundError, ReviewFailedError
from app.services.review import ReviewService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/weekly", response_model=WeeklyReportOut)
async def generate_weekly_report(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WeeklyReportOut:
    """手动生成本周周报（定时任务周日 20:00 也会触发；同周重跑覆盖）。"""
    try:
        return await ReviewService(session).generate_weekly(current_user.id)
    except LLMSettingsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ReviewFailedError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/weekly", response_model=list[WeeklyReportOut])
async def list_weekly_reports(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[WeeklyReportOut]:
    return await ReviewService(session).list_weekly(current_user.id)


@router.get("/weekly/{report_id}", response_model=WeeklyReportOut)
async def get_weekly_report(
    report_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WeeklyReportOut:
    try:
        return await ReviewService(session).get_weekly(current_user.id, report_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="周报不存在") from exc


@router.post("/midweek", response_model=MidweekOut)
async def generate_midweek_brief(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MidweekOut:
    try:
        content = await ReviewService(session).generate_midweek(current_user.id)
    except LLMSettingsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ReviewFailedError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return MidweekOut(content=content)
