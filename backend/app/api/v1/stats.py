"""统计路由（档案 Tab 图表数据源）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.stats import HeatmapOut, HoursOut, SkipReasonsOut, TrendsOut
from app.services.stats import StatsService

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/heatmap", response_model=HeatmapOut)
async def heatmap(
    weeks: int = Query(default=8, ge=1, le=26),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HeatmapOut:
    return await StatsService(session).heatmap(current_user.id, weeks)


@router.get("/trends", response_model=TrendsOut)
async def trends(
    weeks: int = Query(default=8, ge=1, le=26),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TrendsOut:
    return await StatsService(session).trends(current_user.id, weeks)


@router.get("/skip-reasons", response_model=SkipReasonsOut)
async def skip_reasons(
    days: int = Query(default=90, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SkipReasonsOut:
    return await StatsService(session).skip_reasons(current_user.id, days)


@router.get("/hours", response_model=HoursOut)
async def hours(
    days: int = Query(default=90, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HoursOut:
    return await StatsService(session).hours(current_user.id, days)
