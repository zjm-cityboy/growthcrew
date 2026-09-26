"""Alembic 迁移冒烟测试：升级 → 降级 → 再升级。

被测对象是迁移脚本本身（此前 CI 只测 ORM 建表，迁移从未执行过）。
默认用临时 SQLite 文件；设 GC_TEST_DB_URL 时在 PostgreSQL 上验证（与 CI 的 PG 步骤对应）。
"""

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from app.core.db import create_db_engine
from app.models import Base
from sqlalchemy import inspect

_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _drop_existing_tables(url: str) -> None:
    """共享持久库可能有前一轮测试建好的表：清场后交还给 alembic 全权建。"""

    async def _run() -> None:
        eng = create_db_engine(url)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await eng.dispose()

    asyncio.run(_run())


@pytest.fixture
def migration_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    url = os.environ.get("GC_TEST_DB_URL", "")
    if not url or url.startswith("sqlite+aiosqlite://"):
        # 内存库无法跨连接复用，落到临时文件
        url = f"sqlite+aiosqlite:///{tmp_path / 'migration.db'}"
    _drop_existing_tables(url)
    monkeypatch.setenv("GC_DATABASE_URL", url)
    get_settings.cache_clear()
    yield url
    get_settings.cache_clear()


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


def _table_names(url: str) -> set[str]:
    async def _run() -> set[str]:
        eng = create_db_engine(url)
        try:
            async with eng.connect() as conn:
                return set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
        finally:
            await eng.dispose()

    return asyncio.run(_run())


def test_migration_up_down_up(migration_url: str) -> None:
    cfg = _alembic_config()
    expected_tables = {
        "users",
        "refresh_tokens",
        "goals",
        "milestones",
        "weekly_plans",
        "tasks",
        "plan_proposals",
        "daily_journals",
        "life_logs",
        "notifications",
        "user_llm_settings",
        "weekly_reports",
        "push_settings",
        "mistakes",
    }
    command.upgrade(cfg, "head")
    assert expected_tables <= _table_names(migration_url)

    command.downgrade(cfg, "base")
    assert not (expected_tables & _table_names(migration_url))

    command.upgrade(cfg, "head")
    assert expected_tables <= _table_names(migration_url)
