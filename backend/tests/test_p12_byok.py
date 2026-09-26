"""P1.2 BYOK：加密、脱敏、设置 API、prod 守卫。"""

import pytest
from app.core.config import get_settings
from app.core.crypto import CryptoError, decrypt_secret, encrypt_secret, mask_secret
from app.services.llm_settings import LLMSettingsService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from tests.test_p1_core import _auth, _create_user


async def test_crypto_roundtrip() -> None:
    encrypted = encrypt_secret("sk-abc123-def456")
    assert encrypted != "sk-abc123-def456"
    assert decrypt_secret(encrypted) == "sk-abc123-def456"


async def test_crypto_bad_token() -> None:
    with pytest.raises(CryptoError):
        decrypt_secret("not-a-valid-token==")


def test_mask_secret() -> None:
    assert mask_secret("sk-abcdefgh1234") == "sk-***1234"
    assert mask_secret("short") == "***"


async def test_llm_settings_api_flow(client: AsyncClient, engine: AsyncEngine) -> None:
    user_id = await _create_user(engine, "byok_user")
    headers = _auth(user_id)

    saved = await client.put(
        "/api/v1/settings/llm",
        json={
            "base_url": "https://api.siliconflow.cn/v1",
            "api_key": "sk-test-12345678",
            "model_name": "Qwen/Qwen3.5-35B",
        },
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["api_key_masked"].startswith("sk-")
    assert "sk-test-12345678" not in saved.json()["api_key_masked"]

    read = await client.get("/api/v1/settings/llm", headers=headers)
    assert read.status_code == 200
    assert read.json()["model_name"] == "Qwen/Qwen3.5-35B"

    # 库里只有密文：解密还原走通即证明加密存储生效
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        resolved = await LLMSettingsService(session).resolve(user_id)
    assert resolved is not None
    assert resolved.api_key == "sk-test-12345678"

    bad = await client.put(
        "/api/v1/settings/llm",
        json={"base_url": "ftp://x", "api_key": "sk-test-12345678", "model_name": "m"},
        headers=headers,
    )
    assert bad.status_code == 422


def test_prod_requires_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """prod 未配置 GC_ENCRYPTION_KEY 必须启动即失败（BYOK 密钥加密的主密钥）。"""
    get_settings.cache_clear()
    monkeypatch.setenv("GC_ENV", "prod")
    monkeypatch.setenv("GC_JWT_SECRET", "x" * 48)
    monkeypatch.delenv("GC_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GC_ENCRYPTION_KEY"):
        get_settings()
    get_settings.cache_clear()
