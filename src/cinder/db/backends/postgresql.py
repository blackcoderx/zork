from __future__ import annotations

import logging
import os

from .base import DatabaseBackend, DatabaseIntegrityError

logger = logging.getLogger("cinder.db.backends.postgresql")


class PostgreSQLBackend(DatabaseBackend):
    """PostgreSQL database backend using asyncpg connection pool.

    Install: pip install cinder[postgres]   (asyncpg>=0.29.0)

    Parameter style: callers write '?' — this backend converts to $1, $2, ...
    Pool size is configurable via constructor args or env vars:
        CINDER_DB_POOL_MIN  (default: 1)
        CINDER_DB_POOL_MAX  (default: 10)
        CINDER_DB_POOL_TIMEOUT   (default: 30, seconds)
        CINDER_DB_CONNECT_TIMEOUT (default: 10, seconds)

    For NeonDB / Supabase (serverless), append ?sslmode=require to the DSN.
    max_inactive_connection_lifetime=300 keeps connections alive through
    serverless scale-to-zero cycles.
    """

    def __init__(
        self,
        url: str,
        min_size: int | None = None,
        max_size: int | None = None,
        max_inactive_connection_lifetime: float = 300.0,
        ssl: str | None = None,
        statement_timeout: int | None = None,
    ) -> None:
        self._url = url
        self._min_size = min_size or int(os.getenv("CINDER_DB_POOL_MIN", "1"))
        self._max_size = max_size or int(os.getenv("CINDER_DB_POOL_MAX", "10"))
        self._max_inactive_connection_lifetime = max_inactive_connection_lifetime
        self._ssl = ssl
        self._statement_timeout = statement_timeout
        self._pool = None  # asyncpg.Pool, lazily created

    def _convert_sql(self, sql: str) -> str:
        """Replace '?' placeholders with $1, $2, ... (PostgreSQL native style)."""
        parts = sql.split("?")
        return "".join(
            part + (f"${i + 1}" if i < len(parts) - 1 else "")
            for i, part in enumerate(parts)
        )

    async def connect(self) -> None:
        try:
            import asyncpg
        except ImportError as exc:
            raise ImportError(
                "asyncpg is required for PostgreSQL support. "
                "Install it with: pip install cinder[postgres]"
            ) from exc

        connect_timeout = float(os.getenv("CINDER_DB_CONNECT_TIMEOUT", "10"))

        try:
            kwargs: dict = {
                "min_size": self._min_size,
                "max_size": self._max_size,
                "max_inactive_connection_lifetime": self._max_inactive_connection_lifetime,
                "timeout": float(os.getenv("CINDER_DB_POOL_TIMEOUT", "30")),
                "command_timeout": connect_timeout,
            }
            if self._ssl:
                kwargs["ssl"] = self._ssl
            self._pool = await asyncpg.create_pool(self._url, **kwargs)
        except Exception as exc:
            logger.error("PostgreSQL connection failed: %s", exc)
            raise

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _ensure_connected(self) -> None:
        if self._pool is None:
            await self.connect()

    async def execute(self, sql: str, params: tuple = ()) -> None:
        import asyncpg

        await self._ensure_connected()
        sql = self._convert_sql(sql)
        for attempt in range(2):
            try:
                async with self._pool.acquire() as conn:
                    await conn.execute(sql, *params)
                return
            except (asyncpg.UniqueViolationError, asyncpg.IntegrityConstraintViolationError) as exc:
                raise DatabaseIntegrityError(str(exc)) from exc
            except (asyncpg.PostgresConnectionError, asyncpg.TooManyConnectionsError, OSError) as exc:
                if attempt == 0:
                    logger.warning("PostgreSQL connection error (retrying once): %s", exc)
                    continue
                raise

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        import asyncpg

        await self._ensure_connected()
        sql = self._convert_sql(sql)
        for attempt in range(2):
            try:
                async with self._pool.acquire() as conn:
                    row = await conn.fetchrow(sql, *params)
                    return dict(row) if row else None
            except (asyncpg.PostgresConnectionError, asyncpg.TooManyConnectionsError, OSError) as exc:
                if attempt == 0:
                    logger.warning("PostgreSQL connection error (retrying once): %s", exc)
                    continue
                raise

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        import asyncpg

        await self._ensure_connected()
        sql = self._convert_sql(sql)
        for attempt in range(2):
            try:
                async with self._pool.acquire() as conn:
                    rows = await conn.fetch(sql, *params)
                    return [dict(r) for r in rows]
            except (asyncpg.PostgresConnectionError, asyncpg.TooManyConnectionsError, OSError) as exc:
                if attempt == 0:
                    logger.warning("PostgreSQL connection error (retrying once): %s", exc)
                    continue
                raise

    async def table_exists(self, name: str) -> bool:
        row = await self.fetch_one(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ?",
            (name,),
        )
        return row is not None

    async def get_columns(self, name: str) -> list[dict]:
        # Alias column_name → name to match SQLiteBackend contract
        return await self.fetch_all(
            "SELECT column_name AS name, data_type AS type "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = ?",
            (name,),
        )
