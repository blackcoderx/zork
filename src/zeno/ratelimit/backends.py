"""Rate-limit backends for Cinder.

All backends implement :class:`RateLimitBackend`.  Two built-in backends ship:

- :class:`MemoryRateLimitBackend` — sliding-window counter using an in-process
  deque.  Zero dependencies, great for dev/tests, but does NOT share state
  across processes or workers.
- :class:`RedisRateLimitBackend` — atomic token-bucket via a Lua script loaded
  into Redis.  Race-condition safe across any number of workers.

Custom backends: subclass :class:`RateLimitBackend` and pass an instance to
``app.rate_limit.use(my_backend)``.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass

logger = logging.getLogger("cinder.ratelimit.backends")


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_at: float  # UNIX timestamp when the window resets


class RateLimitBackend(ABC):
    """Abstract base for Cinder rate-limit backends."""

    @abstractmethod
    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        """Check whether *key* is within its rate limit.

        Increments the counter atomically and returns the result.
        If *allowed* is ``False`` the request should be rejected with 429.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release any resources held by the backend."""


# ---------------------------------------------------------------------------
# In-memory sliding-window backend
# ---------------------------------------------------------------------------

class MemoryRateLimitBackend(RateLimitBackend):
    """Sliding-window rate limiter using an in-process deque.

    Not safe across multiple processes; intended for development and testing.
    """

    def __init__(self) -> None:
        # key → deque of UNIX timestamps (one entry per request in window)
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = time.monotonic()
        window_start = now - window_seconds
        window = self._windows[key]

        # Evict timestamps older than the window
        while window and window[0] < window_start:
            window.popleft()

        count = len(window)
        reset_at = time.time() + window_seconds  # approximate

        if count >= limit:
            return RateLimitResult(allowed=False, remaining=0, reset_at=reset_at)

        window.append(now)
        return RateLimitResult(
            allowed=True,
            remaining=limit - count - 1,
            reset_at=reset_at,
        )

    async def close(self) -> None:
        self._windows.clear()


# ---------------------------------------------------------------------------
# Redis token-bucket backend
# ---------------------------------------------------------------------------

# Lua script: atomic sliding-window counter using Redis sorted sets.
# KEYS[1] = rate-limit key
# ARGV[1] = current UNIX timestamp (milliseconds, float as string)
# ARGV[2] = window in milliseconds
# ARGV[3] = limit (max requests per window)
# ARGV[4] = unique member for this request (timestamp + random suffix)
#
# Returns: [allowed (0|1), remaining, reset_epoch_ms]
_LUA_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local cutoff = now - window

redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local count = redis.call('ZCARD', key)

if count >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local reset_at = (oldest and oldest[2]) and (tonumber(oldest[2]) + window) or (now + window)
    return {0, 0, reset_at}
end

redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window)
local remaining = limit - count - 1
return {1, remaining, now + window}
"""


class RedisRateLimitBackend(RateLimitBackend):
    """Atomic sliding-window rate limiter backed by Redis sorted sets.

    Requires ``pip install 'cinder[redis]'``.
    Uses a Lua script for atomicity; the script SHA is cached after first load.
    """

    def __init__(self) -> None:
        self._sha: str | None = None

    async def _redis(self):
        from cinder.cache.redis_client import get_client
        return await get_client()

    async def _get_sha(self, r) -> str:
        if self._sha is None:
            self._sha = await r.script_load(_LUA_SCRIPT)
        return self._sha

    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        r = await self._redis()
        now_ms = time.time() * 1000
        window_ms = window_seconds * 1000
        member = f"{now_ms:.3f}-{id(object())}"

        sha = await self._get_sha(r)
        result = await r.evalsha(sha, 1, key, str(now_ms), str(window_ms), str(limit), member)

        allowed = bool(result[0])
        remaining = int(result[1])
        reset_at = float(result[2]) / 1000  # convert ms back to seconds

        return RateLimitResult(allowed=allowed, remaining=remaining, reset_at=reset_at)

    async def close(self) -> None:
        pass  # shared client is closed by redis_client.close()
