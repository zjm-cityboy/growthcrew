"""数据库引擎与会话工厂。

Windows 注意：asyncpg 与 ProactorEventLoop 不兼容，
开发机（win32）必须切到 SelectorEventLoop，否则连接 PG 即报错。
"""

import asyncio
import sys
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def create_db_engine(database_url: str) -> AsyncEngine:
    """按连接串创建异步引擎；内存 SQLite 需要单连接池才能跨会话共享。"""
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            kwargs["poolclass"] = StaticPool
    engine = create_async_engine(database_url, **kwargs)
    if database_url.startswith("sqlite"):
        # SQLite 默认不启用外键约束：不开这个 PRAGMA，所有 ondelete=CASCADE
        # 形同虚设——删父行留下孤儿数据（PG 无此问题，服务端默认执行外键）
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_fk(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """会话工厂：expire_on_commit=False，提交后对象仍可读（API 序列化需要）。"""
    return async_sessionmaker(engine, expire_on_commit=False)
