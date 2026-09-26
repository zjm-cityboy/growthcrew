"""BYOK 密钥加密：Fernet 对称加密，主密钥来自 GC_ENCRYPTION_KEY。

dev 未配置时退化为进程内临时密钥（重启后已存密钥不可解，仅限本地）。
"""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

# 进程级临时密钥：仅 dev 未配置主密钥时兜底
_EPHEMERAL = Fernet(Fernet.generate_key())


class CryptoError(Exception):
    """密文损坏或密钥不匹配。"""


def get_fernet() -> Fernet:
    key = get_settings().encryption_key
    if key:
        return Fernet(key.encode())
    return _EPHEMERAL


def encrypt_secret(plain: str) -> str:
    return get_fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    try:
        return get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise CryptoError("密文无法解密（主密钥可能已更换）") from exc


def mask_secret(plain: str) -> str:
    """脱敏展示：保留前 3 后 4，中间固定省略。"""
    if len(plain) <= 8:
        return "***"
    return f"{plain[:3]}***{plain[-4:]}"
