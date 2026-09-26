"""任务路由：打卡与跳过。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.task import TaskCompleteIn, TaskOut, TaskSkipIn
from app.services.errors import NotFoundError, StateConflictError
from app.services.task import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/{task_id}/complete", response_model=TaskOut)
async def complete_task(
    task_id: int,
    payload: TaskCompleteIn | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TaskOut:
    # body 可省略：打卡按钮常常不带任何参数
    actual_minutes = payload.actual_minutes if payload else None
    try:
        return await TaskService(session).complete(current_user.id, task_id, actual_minutes)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在") from exc
    except StateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{task_id}/skip", response_model=TaskOut)
async def skip_task(
    task_id: int,
    payload: TaskSkipIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TaskOut:
    try:
        return await TaskService(session).skip(current_user.id, task_id, payload.reason)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在") from exc
    except StateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
