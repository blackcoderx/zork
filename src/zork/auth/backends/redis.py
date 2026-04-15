from __future__ import annotations

import time

from zork.cache.redis_client import get_client
from zork.auth.backends.base import TokenBlocklistBackend

KEY_PREFIX = "zork:blocklist:"


class RedisBlocklist(TokenBlocklistBackend):
    """Redis-backed token blocklist with automatic TTL expiration.

    Uses Redis SETEX to store blocked JTIs with TTL matching the token's
    remaining validity. This provides O(1) lookup performance and automatic
    cleanup without manual maintenance.
    """

    def __init__(self, redis_client=None) -> None:
        self._redis = redis_client

    async def _get_redis(self):
        if self._redis is None:
            self._redis = await get_client()
        return self._redis

    async def block(self, jti: str, expires_at: int) -> None:
        redis = await self._get_redis()
        ttl = max(0, int(expires_at) - int(time.time()))
        if ttl > 0:
            await redis.set(f"{KEY_PREFIX}{jti}", b"1", ex=ttl)

    async def is_blocked(self, jti: str) -> bool:
        redis = await self._get_redis()
        return await redis.exists(f"{KEY_PREFIX}{jti}") > 0

    async def cleanup(self) -> int:
        return 0
