"""应用配置：统一从环境变量读取（GC_ 前缀），密钥永不进代码库。

大厂规范要点：
- 配置集中在一个 Settings 类，任何模块不得自行读 os.environ；
- 生产环境密钥缺失/过短/占位符时启动即失败（fail fast），绝不带默认密钥上线。
"""

from functools import lru_cache
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_KEY_PREFIX = "dev-insecure"

# 已在代码库/模板中公开过的占位符，等同已知密钥，生产环境禁止使用
_KNOWN_PLACEHOLDER_SECRETS = {"change_me_to_random_long_string"}

_MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 运行环境：只允许 dev / prod，拼错（如 production）启动即失败
    env: Literal["dev", "prod"] = "dev"

    # 数据库连接（默认本地 SQLite，生产走 PostgreSQL）
    database_url: str = "sqlite+aiosqlite:///./growthcrew.db"

    # 认证（默认值仅供本地开发；生产环境由 get_settings 强制校验）
    jwt_secret: str = f"{_DEV_KEY_PREFIX}-secret-change-me-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # 跨域白名单（JSON 数组字符串，如 ["https://example.com"]）
    cors_origins: list[str] = ["http://localhost:3000"]

    # BYOK 密钥加密主密钥（Fernet，44 位 urlsafe）；空值=dev 每次启动临时生成
    encryption_key: str = ""

    # 定时任务（晨推/晚间提醒，北京时间）；多 worker 部署时只在一个进程启用
    jobs_enabled: bool = True
    morning_brief_hour: int = Field(default=7, ge=0, le=23)  # 晨推时刻（时）
    evening_reminder_hour: int = Field(default=21, ge=0, le=23)  # 晚间提醒（固定 30 分）

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def docs_enabled(self) -> bool:
        """Swagger/OpenAPI 文档仅在开发环境开放（安全 L-2）。"""
        return not self.is_prod


def _validate_prod_secret(settings: Settings) -> None:
    secret = settings.jwt_secret
    too_short = len(secret) < _MIN_SECRET_LENGTH
    is_placeholder = secret.lower() in _KNOWN_PLACEHOLDER_SECRETS
    is_default = secret.startswith(_DEV_KEY_PREFIX)
    if too_short or is_placeholder or is_default:
        msg = (
            f"生产环境 GC_JWT_SECRET 必须是 >= {_MIN_SECRET_LENGTH} 位的随机字符串，"
            "拒绝默认值/空值/占位符"
        )
        raise RuntimeError(msg)


def _validate_prod_encryption_key(settings: Settings) -> None:
    if not settings.encryption_key:
        msg = "生产环境必须设置 GC_ENCRYPTION_KEY（Fernet 主密钥，用于加密用户的 BYOK 密钥）"
        raise RuntimeError(msg)
    try:
        Fernet(settings.encryption_key.encode())
    except ValueError as exc:
        raise RuntimeError("GC_ENCRYPTION_KEY 不是合法的 Fernet 密钥") from exc


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例（lru_cache 保证进程内只构建一次）。"""
    settings = Settings()
    if settings.is_prod:
        _validate_prod_secret(settings)
        _validate_prod_encryption_key(settings)
    return settings
