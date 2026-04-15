from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone

from zork.db.connection import Database

from zork.auth.models import (
    TOKEN_BLOCKLIST_TABLE,
    block_token as db_block_token,
    is_blocked as db_is_blocked,
)
from zork.auth.backends.base import TokenBlocklistBackend


class DatabaseBlocklist(TokenBlocklistBackend):
    """Database-backed token blocklist.

    Uses the existing _token_blocklist table with automatic expiration
    cleanup on startup.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def block(self, jti: str, expires_at: int) -> None:
        expires_str = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
        await db_block_token(self._db, jti, expires_str)

    async def is_blocked(self, jti: str) -> bool:
        return await db_is_blocked(self._db, jti)

    async def cleanup(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        result = await self._db.execute(
            f"DELETE FROM {TOKEN_BLOCKLIST_TABLE} WHERE expires_at < ?", (now,)
        )
        return 1


class HashedTokenBlocklist:
    """Database-backed blocklist that stores hashed JTIs for security.

    Provides additional protection in case the database is compromised,
    since raw JTIs are never stored.
    """

    HASH_TABLE = "_hashed_blocklist"

    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _hash_jti(jti: str) -> str:
        return hashlib.sha256(jti.encode()).hexdigest()

    async def ensure_table(self) -> None:
        await self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.HASH_TABLE} (
                jti_hash TEXT PRIMARY KEY,
                expires_at TEXT NOT NULL
            )
        """)

    async def block(self, jti: str, expires_at: int) -> None:
        hashed = self._hash_jti(jti)
        expires_str = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
        try:
            await self._db.execute(
                f"INSERT INTO {self.HASH_TABLE} (jti_hash, expires_at) VALUES (?, ?)",
                (hashed, expires_str),
            )
        except Exception:
            pass

    async def is_blocked(self, jti: str) -> bool:
        hashed = self._hash_jti(jti)
        row = await self._db.fetch_one(
            f"SELECT jti_hash FROM {self.HASH_TABLE} WHERE jti_hash = ?", (hashed,)
        )
        return row is not None

    async def cleanup(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            f"DELETE FROM {self.HASH_TABLE} WHERE expires_at < ?", (now,)
        )
        return 1
