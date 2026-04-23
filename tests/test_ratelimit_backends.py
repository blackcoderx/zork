"""Tests for rate-limit backends."""

import asyncio
import pytest
from zork.ratelimit.backends import MemoryRateLimitBackend, RedisRateLimitBackend


class TestMemoryRateLimitBackend:
    @pytest.fixture
    def backend(self):
        return MemoryRateLimitBackend()

    async def test_allows_within_limit(self, backend):
        for _ in range(5):
            result = await backend.check("k", limit=5, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 0

    async def test_rejects_over_limit(self, backend):
        for _ in range(5):
            await backend.check("k", limit=5, window_seconds=60)
        result = await backend.check("k", limit=5, window_seconds=60)
        assert result.allowed is False
        assert result.remaining == 0

    async def test_remaining_decrements(self, backend):
        r1 = await backend.check("k", limit=5, window_seconds=60)
        assert r1.remaining == 4
        r2 = await backend.check("k", limit=5, window_seconds=60)
        assert r2.remaining == 3

    async def test_window_resets(self, backend):
        await backend.check("k", limit=2, window_seconds=1)
        await backend.check("k", limit=2, window_seconds=1)
        over = await backend.check("k", limit=2, window_seconds=1)
        assert over.allowed is False

        await asyncio.sleep(1.05)
        result = await backend.check("k", limit=2, window_seconds=1)
        assert result.allowed is True

    async def test_different_keys_independent(self, backend):
        for _ in range(5):
            await backend.check("a", limit=5, window_seconds=60)
        over_a = await backend.check("a", limit=5, window_seconds=60)
        still_ok_b = await backend.check("b", limit=5, window_seconds=60)
        assert over_a.allowed is False
        assert still_ok_b.allowed is True

    async def test_reset_at_is_future(self, backend):
        import time

        result = await backend.check("k", limit=10, window_seconds=60)
        assert result.reset_at > time.time()

    async def test_concurrent_requests_atomic(self, backend):
        """Multiple concurrent checks should not allow more than limit."""
        results = await asyncio.gather(
            *[backend.check("k", limit=5, window_seconds=60) for _ in range(10)]
        )
        allowed = [r for r in results if r.allowed]
        assert len(allowed) == 5

    async def test_close_clears_state(self, backend):
        for _ in range(5):
            await backend.check("k", limit=5, window_seconds=60)
        over = await backend.check("k", limit=5, window_seconds=60)
        assert over.allowed is False

        await backend.close()
        result = await backend.check("k", limit=5, window_seconds=60)
        assert result.allowed is True


# ---------------------------------------------------------------------------
# RedisRateLimitBackend - requires real Redis for testing
# ---------------------------------------------------------------------------
# Note: These tests require a real Redis instance with Lua support.
# They are skipped by default as they need real Redis, not fakeredis.
# To run against real Redis: ensure Redis is running and remove the skip marker.


class TestRedisRateLimitBackend:
    """Tests for RedisRateLimitBackend.

    These tests require a real Redis instance.
    Use @pytest.mark.redis to enable them when Redis is available.
    """

    @pytest.fixture
    def backend(self):
        try:
            from zork.cache.redis_client import get_client

            async def check():
                try:
                    await get_client()
                except RuntimeError:
                    pytest.skip("Redis not configured - set ZORK_REDIS_URL")
                    return None
                return RedisRateLimitBackend()

            import asyncio

            return asyncio.get_event_loop().run_until_complete(check())
        except Exception:
            pytest.skip("Redis not available")

    @pytest.mark.redis
    async def test_allows_within_limit(self, backend):
        await backend.close()  # reset state
        for _ in range(5):
            result = await backend.check("k", limit=5, window_seconds=60)
        assert result.allowed is True

    @pytest.mark.redis
    async def test_rejects_over_limit(self, backend):
        await backend.close()  # reset state
        for _ in range(5):
            await backend.check("k", limit=5, window_seconds=60)
        result = await backend.check("k", limit=5, window_seconds=60)
        assert result.allowed is False

    @pytest.mark.redis
    async def test_concurrent_requests_atomic(self, backend):
        """Multiple concurrent checks should not allow more than limit."""
        await backend.close()  # reset state
        results = await asyncio.gather(
            *[backend.check("k", limit=5, window_seconds=60) for _ in range(10)]
        )
        allowed = [r for r in results if r.allowed]
        assert len(allowed) == 5
