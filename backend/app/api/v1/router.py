"""v1 总路由：新增业务模块在这里挂载。"""

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    export,
    goals,
    health,
    journals,
    life_logs,
    mistakes,
    notifications,
    plans,
    proposals,
    push_settings,
    reports,
    settings,
    stats,
    tasks,
    today,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(goals.router)
api_router.include_router(tasks.router)
api_router.include_router(life_logs.router)
api_router.include_router(journals.router)
api_router.include_router(notifications.router)
api_router.include_router(today.router)
api_router.include_router(settings.router)
api_router.include_router(push_settings.router)
api_router.include_router(plans.router)
api_router.include_router(proposals.router)
api_router.include_router(stats.router)
api_router.include_router(reports.router)
api_router.include_router(export.router)
api_router.include_router(mistakes.router)
