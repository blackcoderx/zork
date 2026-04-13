from __future__ import annotations

from abc import ABC, abstractmethod


class DatabaseIntegrityError(Exception):
    """Raised by all backends when a uniqueness/integrity constraint is violated.

    Replaces driver-specific exceptions (sqlite3.IntegrityError,
    asyncpg.UniqueViolationError, aiomysql.IntegrityError) so callers are
    driver-agnostic.
    """


class DatabaseBackend(ABC):
    """Abstract base for all database driver adapters.

    All methods accept SQL using '?' as the universal placeholder.
    Each backend converts '?' internally to its native style before execution.
    fetch_one and fetch_all always return plain dict / list[dict] — never
    driver Row objects.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Open the connection / pool."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection / pool."""

    @abstractmethod
    async def execute(self, sql: str, params: tuple = ()) -> None:
        """Execute a write statement. Commits immediately.

        Raises DatabaseIntegrityError on UNIQUE/constraint violations.
        """

    @abstractmethod
    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        """Return the first matching row as a dict, or None if not found."""

    @abstractmethod
    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """Return all matching rows as a list of dicts."""

    @abstractmethod
    async def table_exists(self, name: str) -> bool:
        """Return True if a table with the given name exists in the database."""

    @abstractmethod
    async def get_columns(self, name: str) -> list[dict]:
        """Return a list of column descriptors, each with at least a 'name' key."""

    @abstractmethod
    async def get_indexes(self, table: str) -> list[str]:
        """Return names of all indexes on `table` (excluding primary key)."""

    @abstractmethod
    async def index_exists(self, table: str, index_name: str) -> bool:
        """Return True if the named index exists on `table`."""
