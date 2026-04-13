from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlparse

from .base import DatabaseBackend, DatabaseIntegrityError

logger = logging.getLogger("cinder.db.backends.mysql")


class MySQLBackend(DatabaseBackend):
    """MySQL database backend using aiomysql connection pool.

    Install: pip install cinder[mysql]   (aiomysql>=0.2.0)

    Parameter style: callers write '?' — this backend converts to %s.
    Pool size is configurable via constructor args or env vars:
        CINDER_DB_POOL_MIN  (default: 1)
        CINDER_DB_POOL_MAX  (default: 10)

    Accepted URL schemes:
        mysql://user:pass@host:3306/db
        mysql+aiomysql://user:pass@host:3306/db
        mysql+asyncmy://user:pass@host:3306/db

    DDL note: MySQL cannot use bare TEXT as a primary key. This backend
    rewrites TEXT PRIMARY KEY → VARCHAR(36) PRIMARY KEY in CREATE TABLE
    statements (all Cinder id columns are UUID strings, always 36 chars).
    """

    def __init__(
        self,
        url: str,
        min_size: int | None = None,
        max_size: int | None = None,
    ) -> None:
        # Normalise dialect prefixes to a plain mysql:// URL for urlparse
        normalised = url.replace("mysql+aiomysql://", "mysql://").replace(
            "mysql+asyncmy://", "mysql://"
        )
        parsed = urlparse(normalised)
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or 3306
        self._user = parsed.username or "root"
        self._password = parsed.password or ""
        self._db = parsed.path.lstrip("/")
        self._min_size = min_size or int(os.getenv("CINDER_DB_POOL_MIN", "1"))
        self._max_size = max_size or int(os.getenv("CINDER_DB_POOL_MAX", "10"))
        self._pool = None  # aiomysql.Pool, lazily created

    @staticmethod
    def _convert_sql(sql: str) -> str:
        """Replace '?' placeholders with %s (MySQL/Python DB-API style)."""
        return sql.replace("?", "%s")

    @staticmethod
    def _rewrite_ddl(sql: str) -> str:
        """Rewrite TEXT PRIMARY KEY → VARCHAR(36) PRIMARY KEY for MySQL.

        MySQL requires a length prefix for TEXT primary keys. Since Cinder
        always uses UUID strings (exactly 36 chars) as primary keys this
        substitution is always safe.
        """
        if "CREATE TABLE" in sql.upper():
            sql = re.sub(
                r"\bTEXT\s+PRIMARY\s+KEY\b",
                "VARCHAR(36) PRIMARY KEY",
                sql,
                flags=re.IGNORECASE,
            )
        return sql

    async def connect(self) -> None:
        try:
            import aiomysql
        except ImportError as exc:
            raise ImportError(
                "aiomysql is required for MySQL support. "
                "Install it with: pip install cinder[mysql]"
            ) from exc

        connect_timeout = int(os.getenv("CINDER_DB_CONNECT_TIMEOUT", "10"))

        try:
            self._pool = await aiomysql.create_pool(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                db=self._db,
                minsize=self._min_size,
                maxsize=self._max_size,
                cursorclass=aiomysql.DictCursor,
                autocommit=True,
                connect_timeout=connect_timeout,
            )
        except Exception as exc:
            logger.error("MySQL connection failed: %s", exc)
            raise

    async def disconnect(self) -> None:
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    async def _ensure_connected(self) -> None:
        if self._pool is None:
            await self.connect()

    async def execute(self, sql: str, params: tuple = ()) -> None:
        import aiomysql

        await self._ensure_connected()
        sql = self._rewrite_ddl(self._convert_sql(sql))
        for attempt in range(2):
            try:
                async with self._pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(sql, params or ())
                return
            except aiomysql.IntegrityError as exc:
                raise DatabaseIntegrityError(str(exc)) from exc
            except (aiomysql.OperationalError, aiomysql.InternalError) as exc:
                if attempt == 0:
                    logger.warning("MySQL connection error (retrying once): %s", exc)
                    continue
                raise

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        import aiomysql

        await self._ensure_connected()
        sql = self._convert_sql(sql)
        for attempt in range(2):
            try:
                async with self._pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(sql, params or ())
                        return await cur.fetchone()  # DictCursor returns dict
            except (aiomysql.OperationalError, aiomysql.InternalError) as exc:
                if attempt == 0:
                    logger.warning("MySQL connection error (retrying once): %s", exc)
                    continue
                raise

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        import aiomysql

        await self._ensure_connected()
        sql = self._convert_sql(sql)
        for attempt in range(2):
            try:
                async with self._pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(sql, params or ())
                        return await cur.fetchall()
            except (aiomysql.OperationalError, aiomysql.InternalError) as exc:
                if attempt == 0:
                    logger.warning("MySQL connection error (retrying once): %s", exc)
                    continue
                raise

    async def table_exists(self, name: str) -> bool:
        row = await self.fetch_one(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = ?",
            (name,),
        )
        return row is not None

    async def get_columns(self, name: str) -> list[dict]:
        # Alias column_name → name to match SQLiteBackend contract
        return await self.fetch_all(
            "SELECT column_name AS name, data_type AS type "
            "FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = ?",
            (name,),
        )

    async def get_indexes(self, table: str) -> list[str]:
        rows = await self.fetch_all(
            "SELECT DISTINCT index_name FROM information_schema.statistics "
            "WHERE table_schema=DATABASE() AND table_name=? AND index_name != 'PRIMARY'",
            (table,),
        )
        return [r["index_name"] for r in rows]

    async def index_exists(self, table: str, index_name: str) -> bool:
        row = await self.fetch_one(
            "SELECT 1 FROM information_schema.statistics "
            "WHERE table_schema=DATABASE() AND table_name=? AND index_name=? LIMIT 1",
            (table, index_name),
        )
        return row is not None
