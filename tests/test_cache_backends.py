"""Tests for cache backends: MemoryCacheBackend and RedisCacheBackend."""
import asyncio
import pytest
from cinder.cache.backends import MemoryCacheBackend, RedisCacheBackend


# ---------------------------------------------------------------------------
# MemoryCacheBackend
# ---------------------------------------------------------------------------

class TestMemoryCacheBackend:
    @pytest.fixture
    def backend(self):
        return MemoryCacheBackend()

    async def test_set_and_get(self, backend):
        await backend.set("k", b"hello")
        assert await backend.get("k") == b"hello"

    async def test_miss_returns_none(self, backend):
        assert await backend.get("missing") is None

    async def test_delete(self, backend):
        await backend.set("k", b"v")
        await backend.delete("k")
        assert await backend.get("k") is None

    async def test_delete_missing_key_is_noop(self, backend):
        await backend.delete("nope")  # should not raise

    async def test_ttl_expires(self, backend):
        await backend.set("k", b"val", ttl=1)
        assert await backend.get("k") == b"val"
        await asyncio.sleep(1.1)
        assert await backend.get("k") is None

    async def test_delete_pattern(self, backend):
        await backend.set("cache:posts:list:a", b"1")
        await backend.set("cache:posts:list:b", b"2")
        await backend.set("cache:tags:list:c", b"3")
        await backend.delete_pattern("cache:posts:*")
        assert await backend.get("cache:posts:list:a") is None
        assert await backend.get("cache:posts:list:b") is None
        assert await backend.get("cache:tags:list:c") == b"3"

    async def test_sadd_and_smembers(self, backend):
        await backend.sadd("myset", "a", "b", "c")
        members = await backend.smembers("myset")
        assert members == {"a", "b", "c"}

    async def test_sdelete(self, backend):
        await backend.sadd("myset", "x")
        await backend.sdelete("myset")
        assert await backend.smembers("myset") == set()

    async def test_clear(self, backend):
        await backend.set("a", b"1")
        await backend.set("b", b"2")
        await backend.sadd("s", "x")
        await backend.clear()
        assert await backend.get("a") is None
        assert await backend.smembers("s") == set()

    async def test_overwrite_resets_ttl(self, backend):
        await backend.set("k", b"v1", ttl=1)
        await backend.set("k", b"v2", ttl=10)
        await asyncio.sleep(1.1)
        assert await backend.get("k") == b"v2"


# ---------------------------------------------------------------------------
# RedisCacheBackend (using fakeredis)
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis_client():
    try:
        import fakeredis.aioredis as fakeredis  # type: ignore
    except ImportError:
        pytest.skip("fakeredis not installed")
    return fakeredis.FakeRedis(decode_responses=False)


class TestRedisCacheBackend:
    @pytest.fixture(autouse=True)
    def patch_redis(self, monkeypatch, fake_redis_client):
        """Patch _redis() on all RedisCacheBackend instances."""
        async def _r(self):
            return fake_redis_client
        monkeypatch.setattr(RedisCacheBackend, "_redis", _r)

    @pytest.fixture
    def backend(self):
        return RedisCacheBackend(prefix="test")

    async def test_set_and_get(self, backend):
        await backend.set("k", b"hello")
        assert await backend.get("k") == b"hello"

    async def test_miss_returns_none(self, backend):
        assert await backend.get("missing") is None

    async def test_delete(self, backend):
        await backend.set("k", b"v")
        await backend.delete("k")
        assert await backend.get("k") is None

    async def test_sadd_and_smembers(self, backend):
        await backend.sadd("myset", "a", "b")
        members = await backend.smembers("myset")
        assert "a" in members
        assert "b" in members

    async def test_sdelete(self, backend):
        await backend.sadd("myset", "x")
        await backend.sdelete("myset")
        assert await backend.smembers("myset") == set()

    async def test_delete_pattern(self, backend):
        await backend.set("posts:list:1", b"a")
        await backend.set("posts:list:2", b"b")
        await backend.set("tags:list:1", b"c")
        # _k() prepends "test:" — so pass the non-prefixed pattern; _k() adds the prefix internally
        await backend.delete_pattern("posts:*")
        assert await backend.get("posts:list:1") is None
        assert await backend.get("posts:list:2") is None
        assert await backend.get("tags:list:1") == b"c"

    async def test_clear(self, backend):
        await backend.set("a", b"1")
        await backend.set("b", b"2")
        await backend.clear()
        assert await backend.get("a") is None
        assert await backend.get("b") is None
