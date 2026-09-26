"""测试夹具：应用工厂注入 + 数据库（默认内存 SQLite；设 GC_TEST_DB_URL 可跑 PostgreSQL）。"""

import os
from collections.abc import AsyncIterator

import pytest
from app.core.db import create_db_engine
from app.core.ratelimit import login_limiter, register_limiter
from app.main import create_app
from app.models import Base
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

_TEST_DB_URL = os.environ.get("GC_TEST_DB_URL", "sqlite+aiosqlite://")


@pytest.fixture(autouse=True)
def reset_limiters() -> None:
    """每个测试前清空限流计数：测试客户端共享同一 IP，不重置会互相 429。"""
    login_limiter.reset()
    register_limiter.reset()


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_db_engine(_TEST_DB_URL)
    async with eng.begin() as conn:
        # 共享持久库（PG）连续跑测试时先清场；内存库此步为空操作
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    app = create_app(engine=engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
