"""安全原语：密码哈希（argon2id）、JWT 签发校验、刷新令牌生成。

设计要点：
- 密码只存 argon2id 哈希，任何日志不得出现明文密码；
- 刷新令牌为随机串，数据库只存其 SHA-256 摘要（泄漏库也无法还原使用）。
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

from app.core.config import Settings

_password_hasher = PasswordHasher()  # 默认参数即 argon2id

# 随机一次性哈希：对不存在的用户也跑一次校验，抹平两种失败路径的时延差（防账号枚举）
_DUMMY_HASH = _password_hasher.hash(secrets.token_urlsafe(16))


class CredentialsError(Exception):
    """令牌无效或过期。"""


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except Argon2Error:  # 密码不匹配或哈希格式非法，统一返回 False，不泄露原因
        return False


def verify_dummy_password(password: str) -> bool:
    """对随机哈希跑一次校验，仅用于抹平时延，返回值无意义。"""
    return verify_password(password, _DUMMY_HASH)


def create_access_token(user_id: int, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> int:
    """校验 access token 并返回用户 id；无效/过期抛 CredentialsError。"""
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise CredentialsError("invalid or expired token") from exc
    if payload.get("type") != "access" or "sub" not in payload:
        raise CredentialsError("wrong token type")
    try:
        return int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise CredentialsError("invalid subject") from exc


def generate_refresh_token() -> tuple[str, str]:
    """生成刷新令牌，返回 (明文令牌, SHA-256 摘要)。明文只在签发时出现一次。"""
    token = secrets.token_urlsafe(48)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
