"""应用配置：统一从环境变量读取（GC_ 前缀），密钥永不进代码库。

大厂规范要点：
- 配置集中在一个 Settings 类，任何模块不得自行读 os.environ；
- 生产环境密钥缺失/过短/占位符时启动即失败（fail fast），绝不带默认密钥上线。
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_KEY_PREFIX = "dev-insecure"

# SQLite 默认库文件锚定到 backend/ 目录——绝不受启动时工作目录影响。
# 曾因相对路径 ./growthcrew.db 踩坑：从非 backend 目录启动会在该处新建空库，
# 迁移幂等补齐后应用"数据全空"（RAG代码实战 根目录遗留过一个 0 字节空库）。
_BACKEND_DIR = Path(__file__).resolve().parents[2]  # app/core/config.py → backend/
_DEFAULT_SQLITE_URL = f"sqlite+aiosqlite:///{(_BACKEND_DIR / 'growthcrew.db').as_posix()}"

# 已在代码库/模板中公开过的占位符，等同已知密钥，生产环境禁止使用
_KNOWN_PLACEHOLDER_SECRETS = {"change_me_to_random_long_string"}

_MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GC_",
        # 锚定 backend/.env 绝对路径：相对路径随 CWD 漂移时，配置会被静默
        # 回落到仓库公开的 dev 默认密钥（SQLite 默认值已因同类坑锚定过）
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 运行环境：只允许 dev / prod，拼错（如 production）启动即失败
    env: Literal["dev", "prod"] = "dev"

    # 数据库连接（默认本地 SQLite——绝对路径锚定 backend/，生产走 PostgreSQL）
    database_url: str = _DEFAULT_SQLITE_URL

    # 认证（默认值仅供本地开发；生产环境由 get_settings 强制校验）
    jwt_secret: str = f"{_DEV_KEY_PREFIX}-secret-change-me-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # 跨域白名单（JSON 数组字符串，如 ["https://example.com"]）。
    # 前端 dev 端口 3211：3100 落在 Windows Hyper-V 动态保留段（3031-3130），
    # 与 Docker 部署端口统一为 3211
    cors_origins: list[str] = ["http://localhost:3211", "http://127.0.0.1:3211"]

    # BYOK 密钥加密主密钥（Fernet，44 位 urlsafe）；空值=dev 每次启动临时生成
    encryption_key: str = ""

    # 定时任务（晨推/晚间提醒，北京时间）；多 worker 部署时只在一个进程启用
    jobs_enabled: bool = True
    morning_brief_hour: int = Field(default=7, ge=0, le=23)  # 晨推时刻（时）
    evening_reminder_hour: int = Field(default=21, ge=0, le=23)  # 晚间提醒（固定 30 分）

    # 演示模式：开启后 /dev/clock 时间快进可用（面试演示"第二天"闭环）；
    # 覆盖值仅存进程内存，重启即回真实时间。prod 强制拒绝开启。
    demo_mode: bool = False

    # 管理员用户名（JSON 数组）：匹配者可访问 /admin 管理后台（看全部用户、
    # 清数据、审计提案）。部署者在 .env 里指定，未配置 = 无管理员。
    admin_usernames: list[str] = Field(default_factory=list)

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
        if settings.demo_mode:
            raise RuntimeError("生产环境禁止开启 GC_DEMO_MODE（时间快进后门）")
    return settings
