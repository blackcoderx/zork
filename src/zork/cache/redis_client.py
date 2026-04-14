"""Shared async Redis client factory.

A single ``redis.asyncio.Redis`` instance is created lazily on first access
and reused across all Zork subsystems (cache, rate-limit, realtime broker).

Usage::

    from zork.cache.redis_client import get_client, configure, close

    configure(url="redis://localhost:6379/0")
    client = await get_client()   # connects on first call
    await close()                 # called during app shutdown
"""

from __future__ import annotations

import logging

logger = logging.getLogger("zork.cache.redis_client")

_url: str | None = None
_client = None  # redis.asyncio.Redis | None


def configure(url: str) -> None:
    """Set the Redis URL before the first ``get_client()`` call."""
    global _url, _client
    _url = url
    _client = None  # reset so next get_client() reconnects with new URL


async def get_client():
    """Return the shared async Redis client, creating it on first call.

    Raises ``ImportError`` with a helpful message if ``redis`` is not installed.
    Raises ``RuntimeError`` if :func:`configure` has not been called.
    """
    global _client
    if _client is not None:
        return _client

    if _url is None:
        raise RuntimeError(
            "Redis URL not configured. Call configure(url=...) or set "
            "ZORK_REDIS_URL before using Redis-backed features."
        )

    try:
        import redis.asyncio as aioredis  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "Redis client not installed. Install it with: pip install 'zork[redis]'"
        ) from exc

    _client = aioredis.from_url(
        _url,
        encoding="utf-8",
        decode_responses=False,  # we handle bytes ourselves
    )
    logger.info("Redis client created: %s", _url)
    return _client


async def close() -> None:
    """Close the shared Redis client. Called during app shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("Redis client closed")
