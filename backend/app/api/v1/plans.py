"""计划导入路由：一次性 JSON 与 SSE 流式两个入口。

/import        一次性返回（API 调用方与既有测试使用）。
/import/stream 服务器推送事件流：教练每一步实时下发，done 事件携带完整结果；
               前端用它渲染过程时间线（Agent 过程可观测性）。
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.proposal import ImportOut, ImportPlanIn
from app.services.errors import LLMSettingsError, NotFoundError, PlannerFailedError
from app.services.plan_import import PlanImportService

router = APIRouter(prefix="/plans", tags=["plans"])
logger = logging.getLogger(__name__)


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


@router.post("/import/stream")
async def import_plan_stream(
    payload: ImportPlanIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """SSE 版导入：Agent 在后台任务里跑，过程事件经队列实时下发。

    流开始后 HTTP 状态恒为 200，业务失败通过 error 事件传达（code 对应
    /import 的 404/400/502 语义），前端据此复用原有错误展示逻辑。
    """
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def run() -> None:
        try:
            result = await PlanImportService(session).start(
                current_user.id, payload, on_event=queue.put_nowait
            )
            queue.put_nowait({"type": "done", "result": result.model_dump(mode="json")})
        except NotFoundError:
            queue.put_nowait({"type": "error", "code": "not_found", "message": "目标不存在"})
        except LLMSettingsError as exc:
            queue.put_nowait({"type": "error", "code": "need_settings", "message": str(exc)})
        except PlannerFailedError as exc:
            queue.put_nowait({"type": "error", "code": "planner", "message": str(exc)})
        except Exception:
            # catch-all：DB 故障/编排层意外异常若不投递终止事件，流会永久
            # 挂在 queue.get() 上（前端永不触发错误展示，后台 task 无人认领异常）
            logger.exception("SSE 导入意外异常（user_id=%s）", current_user.id)
            queue.put_nowait(
                {"type": "error", "code": "internal", "message": "服务内部错误，请稍后重试"}
            )

    # 保存任务引用防 GC（RUF006）；stream 闭包持有它，客户端断开时取消回收
    task = asyncio.create_task(run())

    async def stream() -> AsyncIterator[str]:
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in ("done", "error"):
                    return
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
