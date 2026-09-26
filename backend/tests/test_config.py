"""配置校验测试：生产密钥红线（fail fast）。"""

import pytest
from app.core.config import get_settings
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch: pytest.MonkeyPatch):
    """config 是 lru_cache 单例：每个用例前后清缓存，避免串扰。"""
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_dev_default_secret_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GC_ENV", raising=False)
    monkeypatch.delenv("GC_JWT_SECRET", raising=False)
    settings = get_settings()
    assert settings.env == "dev"


def test_prod_rejects_short_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GC_ENV", "prod")
    monkeypatch.setenv("GC_JWT_SECRET", "short")
    with pytest.raises(RuntimeError, match="GC_JWT_SECRET"):
        get_settings()


def test_prod_rejects_placeholder_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GC_ENV", "prod")
    monkeypatch.setenv("GC_JWT_SECRET", "CHANGE_ME_TO_RANDOM_LONG_STRING")
    with pytest.raises(RuntimeError, match="GC_JWT_SECRET"):
        get_settings()


def test_invalid_env_value_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """GC_ENV 拼写错误（如 production）必须启动即失败，而不是静默当成开发环境。"""
    monkeypatch.setenv("GC_ENV", "production")
    with pytest.raises(ValidationError):
        get_settings()
