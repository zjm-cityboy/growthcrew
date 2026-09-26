"""进程内滑动窗口限流器。

当前单实例部署够用；将来多实例部署需替换为 Redis 实现（接口不变）。
"""

import time
from asyncio import Lock
from collections import deque

_MAX_REQUESTS = 10
_REGISTER_MAX_REQUESTS = 3
_WINDOW_SECONDS = 60.0
_PURGE_THRESHOLD = 4096  # 活跃键数超阈值时清理过期键，防止内存只增不减


class SlidingWindowLimiter:
    def __init__(
        self, max_requests: int = _MAX_REQUESTS, window_seconds: float = _WINDOW_SECONDS
    ) -> None:
        self._max_requests = max_requests
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    async def allow(self, key: str) -> bool:
        """请求是否放行。key 形如 "login:ip:1.2.3.4"。"""
        now = time.monotonic()
        async with self._lock:
            if len(self._hits) > _PURGE_THRESHOLD:
                self._purge(now)
            hits = self._hits.setdefault(key, deque[float]())
            while hits and hits[0] <= now - self._window:
                hits.popleft()
            if len(hits) >= self._max_requests:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        """清空全部计数（测试隔离用）。"""
        self._hits.clear()

    def _purge(self, now: float) -> None:
        stale = [
            key for key, hits in self._hits.items() if not hits or hits[-1] <= now - self._window
        ]
        for key in stale:
            del self._hits[key]


# 登录：IP 桶（挡分布式撞库）+ 用户名桶（挡单账号定向爆破），双桶见 api/v1/auth.py
login_limiter = SlidingWindowLimiter(max_requests=_MAX_REQUESTS)

# 注册：argon2 哈希是 CPU 密集操作且无需认证，限额更紧
register_limiter = SlidingWindowLimiter(max_requests=_REGISTER_MAX_REQUESTS)
