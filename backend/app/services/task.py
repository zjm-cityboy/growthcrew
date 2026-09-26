"""任务业务：打卡（幂等）与跳过（带卡因）。

并发安全：complete/skip 用条件 UPDATE 原子翻转状态（QA C-1 修复），
并发"complete + skip 同一任务"只有一个成功，另一个返回 409。
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SkipReason, TaskStatus
from app.models.plan import Task
from app.repositories.plan import TaskRepository
from app.schemas.task import TaskOut
from app.services.errors import NotFoundError, StateConflictError


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self._tasks = TaskRepository(session)
        self._session = session

    async def complete(self, user_id: int, task_id: int, actual_minutes: int | None) -> TaskOut:
        task = await self._require_task(task_id, user_id)

        if task.status == TaskStatus.DONE:
            # 幂等：重复点完成直接返回（可更新时长）
            if actual_minutes is not None:
                task.actual_minutes = actual_minutes
                await self._session.commit()
            return TaskOut.model_validate(task)

        if task.status == TaskStatus.SKIPPED:
            raise StateConflictError("已跳过的任务不能标记完成")

        # 原子翻转：并发 complete vs skip 只有一个成功
        updated = await self._tasks.transition_status(
            task_id,
            user_id,
            from_status=TaskStatus.TODO,
            to_status=TaskStatus.DONE,
            completed_at=datetime.now(UTC),
        )
        if updated is None:
            raise StateConflictError("该任务状态已被其他操作修改")
        if actual_minutes is not None:
            updated.actual_minutes = actual_minutes
        await self._session.commit()
        return TaskOut.model_validate(updated)

    async def skip(self, user_id: int, task_id: int, reason: SkipReason) -> TaskOut:
        task = await self._require_task(task_id, user_id)
        if task.status == TaskStatus.DONE:
            raise StateConflictError("已完成的任务不能跳过")

        # 原子翻转：TODO→SKIPPED 或 SKIPPED→SKIPPED（可改卡因）
        from_status = task.status  # TODO 或 SKIPPED（重选卡因）
        updated = await self._tasks.transition_status(
            task_id,
            user_id,
            from_status=from_status,
            to_status=TaskStatus.SKIPPED,
            skip_reason=reason,
            skipped_at=datetime.now(UTC),
        )
        if updated is None:
            raise StateConflictError("该任务状态已被其他操作修改")
        await self._session.commit()
        return TaskOut.model_validate(updated)

    async def _require_task(self, task_id: int, user_id: int) -> Task:
        task = await self._tasks.get_for_user(task_id, user_id)
        if task is None:
            raise NotFoundError("任务不存在")
        return task
