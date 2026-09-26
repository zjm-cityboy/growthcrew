"""计划导入路由。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.proposal import ImportOut, ImportPlanIn
from app.services.errors import LLMSettingsError, NotFoundError, PlannerFailedError
from app.services.plan_import import PlanImportService

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("/import", response_model=ImportOut)
async def import_plan(
    payload: ImportPlanIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ImportOut:
    try:
        return await PlanImportService(session).start(current_user.id, payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标不存在") from exc
    except LLMSettingsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PlannerFailedError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
