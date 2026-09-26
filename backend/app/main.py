"""应用工厂与入口（uvicorn app.main:app）。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.db import create_db_engine, create_session_maker

try:  # jobs 依赖组未安装时应用仍可运行（GC_JOBS_ENABLED=true 时启动即报错）
    from app.jobs.scheduler import build_scheduler
except ImportError:  # pragma: no cover - 依赖缺失分支
    build_scheduler = None  # type: ignore[assignment]


def create_app(
    settings: Settings | None = None,
    engine: AsyncEngine | None = None,
) -> FastAPI:
    """构建应用。engine 参数供测试注入内存库；生产从配置构建。"""
    app_settings = settings or get_settings()
    app_engine = engine or create_db_engine(app_settings.database_url)
    session_maker = create_session_maker(app_engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        scheduler = None
        if app_settings.jobs_enabled:
            if build_scheduler is None:
                msg = "GC_JOBS_ENABLED=true 但未安装 jobs 依赖组（pip install -e '.[jobs]'）"
                raise RuntimeError(msg)
            scheduler = build_scheduler(session_maker, app_settings)
            scheduler.start()
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        # 关闭推送客户端（httpx 连接池），避免 shutdown 资源告警
        from app.services.push import _HTTP

        await _HTTP.aclose()
        await app_engine.dispose()

    app = FastAPI(
        title="GrowthCrew API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs" if app_settings.docs_enabled else None,
        openapi_url="/api/openapi.json" if app_settings.docs_enabled else None,
    )
    app.state.settings = app_settings
    app.state.engine = app_engine
    app.state.session_maker = session_maker

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
