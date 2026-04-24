"""Cache backends for Zork.

All backends implement :class:`CacheBackend`.  Two built-in backends ship:

- :class:`MemoryCacheBackend` — in-process dict; zero config, great for dev/tests.
- :class:`RedisCacheBackend` — Redis-backed; production-grade, multi-process safe.

Custom backends: subclass :class:`CacheBackend` and pass an instance to
``app.cache.use(my_backend)``.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("zork.cache.backends")


class CacheBackend(ABC):
    """Abstract base for Zork cache backends."""

    @abstractmethod
    async def get(self, key: str) -> bytes | None:
        """Return cached bytes for *key*, or ``None`` on miss."""

    @abstractmethod
    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        """Store *value* under *key* with optional TTL in seconds."""

    @abstractmethod
    async def delete(self, *keys: str) -> None:
        """Delete one or more keys. Missing keys are silently ignored."""

    @abstractmethod
    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching *pattern* (glob-style, e.g. ``cache:posts:*``)."""

    @abstractmethod
    async def sadd(self, set_key: str, *members: str) -> None:
        """Add *members* to a Redis-style set stored at *set_key*."""

    @abstractmethod
    async def smembers(self, set_key: str) -> set[str]:
        """Return all members of the set stored at *set_key*."""

    @abstractmethod
    async def sdelete(self, set_key: str) -> None:
        """Delete the set stored at *set_key*."""

    @abstractmethod
    async def clear(self) -> None:
        """Remove all keys managed by this backend."""

    @abstractmethod
    async def close(self) -> None:
        """Release any resources held by the backend."""


# ---------------------------------------------------------------------------
# In-memory backend
# ---------------------------------------------------------------------------


class MemoryCacheBackend(CacheBackend):
    """Thread-safe, asyncio-compatible in-memory cache.

    Uses a plain dict with per-entry expiry tracked by ``asyncio.get_event_loop().call_later``.
    Good for development and testing; does NOT share state across processes.
    """

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self._sets: dict[str, set[str]] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}

    async def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        self._store[key] = value
        # Cancel any existing expiry
        if key in self._timers:
            self._timers[key].cancel()
            del self._timers[key]
        if ttl is not None and ttl > 0:
            loop = asyncio.get_event_loop()
            self._timers[key] = loop.call_later(ttl, self._expire, key)

    def _expire(self, key: str) -> None:
        self._store.pop(key, None)
        self._timers.pop(key, None)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._store.pop(key, None)
            if key in self._timers:
                self._timers[key].cancel()
                del self._timers[key]

    async def delete_pattern(self, pattern: str) -> None:
        import fnmatch

        matched = [k for k in self._store if fnmatch.fnmatch(k, pattern)]
        await self.delete(*matched)

    async def sadd(self, set_key: str, *members: str) -> None:
        self._sets.setdefault(set_key, set()).update(members)

    async def smembers(self, set_key: str) -> set[str]:
        return set(self._sets.get(set_key, set()))

    async def sdelete(self, set_key: str) -> None:
        self._sets.pop(set_key, None)

    async def clear(self) -> None:
        for handle in self._timers.values():
            handle.cancel()
        self._store.clear()
        self._sets.clear()
        self._timers.clear()

    async def close(self) -> None:
        await self.clear()


# ---------------------------------------------------------------------------
# Redis backend
# ---------------------------------------------------------------------------


class RedisCacheBackend(CacheBackend):
    """Redis-backed cache using the shared Zork Redis client.

    Requires ``pip install 'zork[redis]'``.

    All keys are namespaced under *prefix* (default ``"zork"``).
    """

    def __init__(self, *, prefix: str = "zork") -> None:
        self._prefix = prefix

    def _k(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def _redis(self):
        from zork.cache.redis_client import get_client

        return await get_client()

    async def get(self, key: str) -> bytes | None:
        r = await self._redis()
        return await r.get(self._k(key))

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        r = await self._redis()
        if ttl:
            await r.setex(self._k(key), ttl, value)
        else:
            await r.set(self._k(key), value)

    async def delete(self, *keys: str) -> None:
        if not keys:
            return
        r = await self._redis()
        await r.delete(*[self._k(k) for k in keys])

    async def delete_pattern(self, pattern: str) -> None:
        r = await self._redis()
        full_pattern = self._k(pattern)
        cursor = 0
        keys_to_delete: list[bytes] = []
        while True:
            cursor, keys = await r.scan(cursor, match=full_pattern, count=100)
            keys_to_delete.extend(keys)
            if cursor == 0:
                break
        if keys_to_delete:
            await r.delete(*keys_to_delete)

    async def sadd(self, set_key: str, *members: str) -> None:
        r = await self._redis()
        await r.sadd(self._k(set_key), *members)

    async def smembers(self, set_key: str) -> set[str]:
        r = await self._redis()
        raw = await r.smembers(self._k(set_key))
        return {m.decode() if isinstance(m, bytes) else m for m in raw}

    async def sdelete(self, set_key: str) -> None:
        r = await self._redis()
        await r.delete(self._k(set_key))

    async def clear(self) -> None:
        r = await self._redis()
        cursor = 0
        while True:
            cursor, keys = await r.scan(cursor, match=f"{self._prefix}:*", count=100)
            if keys:
                await r.delete(*keys)
            if cursor == 0:
                break

    async def close(self) -> None:
        pass  # shared client is closed by redis_client.close()
