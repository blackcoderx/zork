from __future__ import annotations

import logging

import aiosqlite

from .base import DatabaseBackend, DatabaseIntegrityError

logger = logging.getLogger("cinder.db.backends.sqlite")


class SQLiteBackend(DatabaseBackend):
    """SQLite database backend using aiosqlite.

    Supports WAL mode for concurrent reads and returns rows as plain dicts.
    Auto-connects on first use if not explicitly connected.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self._connection is not None:
            return
        self._connection = await aiosqlite.connect(self._path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        await self._connection.commit()

    async def disconnect(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _ensure_connected(self) -> None:
        if self._connection is None:
            await self.connect()

    async def execute(self, sql: str, params: tuple = ()) -> None:
        await self._ensure_connected()
        try:
            await self._connection.execute(sql, params)
            await self._connection.commit()
        except Exception as exc:
            # aiosqlite wraps sqlite3 exceptions; check by name for portability
            if "IntegrityError" in type(exc).__name__:
                raise DatabaseIntegrityError(str(exc)) from exc
            raise

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        await self._ensure_connected()
        cursor = await self._connection.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        await self._ensure_connected()
        cursor = await self._connection.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def table_exists(self, name: str) -> bool:
        row = await self.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        )
        return row is not None

    async def get_columns(self, name: str) -> list[dict]:
        # PRAGMA cannot use ? placeholders; table name comes from Collection
        # definitions (never from user input), so this is safe.
        return await self.fetch_all(f"PRAGMA table_info({name})")
        # Each row has a 'name' key — matches the contract expected by store.py

    async def get_indexes(self, table: str) -> list[str]:
        rows = await self.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND name NOT LIKE 'sqlite_%'",
            (table,),
        )
        return [r["name"] for r in rows]

    async def index_exists(self, table: str, index_name: str) -> bool:
        row = await self.fetch_one(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND tbl_name=? AND name=?",
            (table, index_name),
        )
        return row is not None
