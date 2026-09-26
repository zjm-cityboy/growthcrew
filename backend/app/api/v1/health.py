"""健康检查：live（进程活着）/ ready（数据库连通）。部署与监控都依赖它们。"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.api.deps import get_session
from app.repositories.system import SystemRepository

router = APIRouter(prefix="/health", tags=["health"])


class HealthOut(BaseModel):
    status: str
    version: str = __version__


class ReadyOut(HealthOut):
    database: str


@router.get("/live", response_model=HealthOut)
async def live() -> HealthOut:
    return HealthOut(status="ok")


@router.get("/ready", response_model=ReadyOut)
async def ready(session: AsyncSession = Depends(get_session)) -> ReadyOut:
    if not await SystemRepository(session).ping():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    return ReadyOut(status="ok", database="up")
