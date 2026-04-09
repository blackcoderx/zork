from __future__ import annotations

from cinder.db.backends import resolve_backend
from cinder.db.backends.base import DatabaseBackend


class Database:
    """Multi-database connection manager.

    Accepts a URL or a bare SQLite file path (backward compatible):
        "app.db"                           → SQLite (default, zero config)
        "sqlite:///app.db"                 → SQLite
        "postgresql://user:pass@host/db"   → PostgreSQL (requires asyncpg)
        "postgres://user:pass@host/db"     → PostgreSQL (requires asyncpg)
        "mysql://user:pass@host/db"        → MySQL (requires aiomysql)

    Environment variables override the programmatic value:
        CINDER_DATABASE_URL   — highest priority (Cinder-specific)
        DATABASE_URL          — second priority (standard PaaS convention)

    Pool size (PostgreSQL / MySQL):
        CINDER_DB_POOL_MIN    — minimum connections (default: 1)
        CINDER_DB_POOL_MAX    — maximum connections (default: 10)
        CINDER_DB_POOL_TIMEOUT    — seconds to wait for a free connection (default: 30)
        CINDER_DB_CONNECT_TIMEOUT — seconds to open a new connection (default: 10)
    """

    def __init__(self, url: str = "app.db"):
        self.url = url
        self._backend: DatabaseBackend = resolve_backend(url)

    async def connect(self) -> None:
        await self._backend.connect()

    async def disconnect(self) -> None:
        await self._backend.disconnect()

    async def execute(self, sql: str, params: tuple = ()) -> None:
        await self._backend.execute(sql, params)

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        return await self._backend.fetch_one(sql, params)

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        return await self._backend.fetch_all(sql, params)

    async def table_exists(self, name: str) -> bool:
        """Return True if a table with the given name exists."""
        return await self._backend.table_exists(name)

    async def get_columns(self, name: str) -> list[dict]:
        """Return column descriptors for the given table (each has a 'name' key)."""
        return await self._backend.get_columns(name)

    async def get_indexes(self, table: str) -> list[str]:
        """Return names of all indexes on `table` (excluding primary key)."""
        return await self._backend.get_indexes(table)

    async def index_exists(self, table: str, index_name: str) -> bool:
        """Return True if the named index exists on `table`."""
        return await self._backend.index_exists(table, index_name)
