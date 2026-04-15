"""Tests for token blocklist backends.

Covers:
- DatabaseBlocklist operations (block, is_blocked, cleanup)
- RedisBlocklist operations (block, is_blocked, cleanup)
- HashedTokenBlocklist for secure JTI storage
"""

import time
import pytest
import pytest_asyncio

from zork.auth.backends import (
    DatabaseBlocklist,
    HashedTokenBlocklist,
    RedisBlocklist,
    TokenBlocklistBackend,
)
from zork.auth.models import create_auth_tables
from zork.db.connection import Database


class TestDatabaseBlocklist:
    @pytest_asyncio.fixture
    async def db(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        await db.connect()
        await create_auth_tables(db)
        yield db
        await db.disconnect()

    @pytest_asyncio.fixture
    def blocklist(self, db):
        return DatabaseBlocklist(db)

    @pytest.mark.asyncio
    async def test_block_and_is_blocked(self, blocklist):
        jti = "test-jti-123"
        expires_at = 1735689600  # 2025-01-01 00:00:00 UTC

        assert await blocklist.is_blocked(jti) is False
        await blocklist.block(jti, expires_at)
        assert await blocklist.is_blocked(jti) is True

    @pytest.mark.asyncio
    async def test_block_duplicate_is_idempotent(self, blocklist):
        jti = "test-jti-456"
        expires_at = 1735689600

        await blocklist.block(jti, expires_at)
        await blocklist.block(jti, expires_at)  # Should not raise

        assert await blocklist.is_blocked(jti) is True

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired(self, blocklist, db):
        from datetime import datetime, timezone, timedelta

        jti_expired = "expired-jti"
        jti_valid = "valid-jti"
        now = datetime.now(timezone.utc)

        past = (now - timedelta(hours=1)).isoformat()
        future = (now + timedelta(hours=1)).isoformat()

        await db.execute(
            "INSERT INTO _token_blocklist (jti, expires_at) VALUES (?, ?)",
            (jti_expired, past),
        )
        await db.execute(
            "INSERT INTO _token_blocklist (jti, expires_at) VALUES (?, ?)",
            (jti_valid, future),
        )

        removed = await blocklist.cleanup()
        assert removed >= 1

        assert await blocklist.is_blocked(jti_expired) is False
        assert await blocklist.is_blocked(jti_valid) is True

    @pytest.mark.asyncio
    async def test_is_blocked_nonexistent_returns_false(self, blocklist):
        assert await blocklist.is_blocked("nonexistent-jti") is False


class TestHashedTokenBlocklist:
    @pytest_asyncio.fixture
    async def db(self, tmp_path):
        db = Database(str(tmp_path / "test_hashed.db"))
        await db.connect()
        yield db
        await db.disconnect()

    @pytest_asyncio.fixture
    def blocklist(self, db):
        bl = HashedTokenBlocklist(db)
        return bl

    @pytest.mark.asyncio
    async def test_ensure_table_creates_table(self, db, blocklist):
        await blocklist.ensure_table()
        row = await db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (blocklist.HASH_TABLE,),
        )
        assert row is not None

    @pytest.mark.asyncio
    async def test_block_stores_hash(self, db, blocklist):
        jti = "sensitive-jti-value"
        expires_at = 1735689600

        await blocklist.ensure_table()
        await blocklist.block(jti, expires_at)

        row = await db.fetch_one(f"SELECT * FROM {blocklist.HASH_TABLE}")
        assert row is not None
        assert row["jti_hash"] != jti  # Should be hashed

    @pytest.mark.asyncio
    async def test_is_blocked_with_hash(self, blocklist):
        jti = "test-hashed-jti"
        expires_at = 1735689600

        await blocklist.ensure_table()
        await blocklist.block(jti, expires_at)

        assert await blocklist.is_blocked(jti) is True
        assert await blocklist.is_blocked("wrong-jti") is False

    @pytest.mark.asyncio
    async def test_hash_jti_is_deterministic(self, blocklist):
        jti = "same-jti"
        h1 = blocklist._hash_jti(jti)
        h2 = blocklist._hash_jti(jti)
        assert h1 == h2

    @pytest.mark.asyncio
    async def test_different_jtis_produce_different_hashes(self, blocklist):
        h1 = blocklist._hash_jti("jti-1")
        h2 = blocklist._hash_jti("jti-2")
        assert h1 != h2


class TestRedisBlocklist:
    @pytest.fixture
    async def fake_redis(self):
        try:
            import fakeredis.aioredis as fakeredis
        except ImportError:
            pytest.skip("fakeredis not installed")
        r = fakeredis.FakeRedis(decode_responses=False)
        yield r
        await r.aclose()

    @pytest.fixture
    def blocklist(self, fake_redis):
        return RedisBlocklist(redis_client=fake_redis)

    @pytest.mark.asyncio
    async def test_block_and_is_blocked(self, blocklist, fake_redis):
        jti = "redis-jti-123"
        future_time = int(time.time()) + 3600

        assert await blocklist.is_blocked(jti) is False
        await blocklist.block(jti, future_time)
        assert await blocklist.is_blocked(jti) is True

    @pytest.mark.asyncio
    async def test_is_blocked_nonexistent_returns_false(self, blocklist):
        assert await blocklist.is_blocked("nonexistent-jti") is False

    @pytest.mark.asyncio
    async def test_ttl_is_set_correctly(self, blocklist, fake_redis):
        jti = "ttl-test-jti"
        future_time = int(time.time()) + 3600

        await blocklist.block(jti, future_time)

        ttl = await fake_redis.ttl(f"zork:blocklist:{jti}")
        assert ttl > 0
        assert ttl <= 3600

    @pytest.mark.asyncio
    async def test_expired_key_auto_removed(self, blocklist, fake_redis):
        jti = "expired-redis-jti"
        past_time = int(time.time()) - 1  # Already expired

        await blocklist.block(jti, past_time)
        assert await blocklist.is_blocked(jti) is False

    @pytest.mark.asyncio
    async def test_duplicate_block_updates_ttl(self, blocklist, fake_redis):
        jti = "update-ttl-jti"
        future_time1 = int(time.time()) + 3600
        future_time2 = int(time.time()) + 7200

        await blocklist.block(jti, future_time1)
        ttl1 = await fake_redis.ttl(f"zork:blocklist:{jti}")

        await blocklist.block(jti, future_time2)
        ttl2 = await fake_redis.ttl(f"zork:blocklist:{jti}")

        assert ttl2 > ttl1

    @pytest.mark.asyncio
    async def test_cleanup_returns_zero(self, blocklist):
        result = await blocklist.cleanup()
        assert result == 0


class TestTokenBlocklistBackendInterface:
    @pytest_asyncio.fixture
    async def db(self, tmp_path):
        db = Database(str(tmp_path / "interface_test.db"))
        await db.connect()
        await create_auth_tables(db)
        yield db
        await db.disconnect()

    def test_database_blocklist_implements_interface(self, db):
        bl = DatabaseBlocklist(db)
        assert isinstance(bl, TokenBlocklistBackend)

    def test_redis_blocklist_implements_interface(self):
        bl = RedisBlocklist()
        assert isinstance(bl, TokenBlocklistBackend)

    def test_hashed_blocklist_not_interface(self, db):
        bl = HashedTokenBlocklist(db)
        assert not isinstance(bl, TokenBlocklistBackend)
