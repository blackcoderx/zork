from __future__ import annotations

import os

from .base import DatabaseBackend, DatabaseIntegrityError

_POSTGRES = ("postgresql://", "postgres://", "postgresql+asyncpg://")
_MYSQL = ("mysql://", "mysql+aiomysql://", "mysql+asyncmy://")


def resolve_backend(url: str) -> DatabaseBackend:
    """Return the correct DatabaseBackend for the given URL.

    Resolution priority (highest → lowest):
    1. CINDER_DATABASE_URL env var   (Cinder-specific override)
    2. DATABASE_URL env var          (standard PaaS convention)
    3. Programmatic ``url`` argument
    4. Default: "app.db" (SQLite, zero config)

    Supported URL forms:
        "app.db"                          → SQLite (bare path)
        "sqlite:///app.db"                → SQLite
        "postgresql://user:pass@host/db"  → PostgreSQL (requires asyncpg)
        "postgres://user:pass@host/db"    → PostgreSQL (requires asyncpg)
        "mysql://user:pass@host/db"       → MySQL (requires aiomysql)
        "mysql+aiomysql://..."            → MySQL (requires aiomysql)
        "mysql+asyncmy://..."             → MySQL (requires aiomysql)

    Drivers are imported lazily — SQLite users never need asyncpg or aiomysql
    installed.
    """
    effective_url: str = (
        os.getenv("CINDER_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or url
    )

    lower = effective_url.lower()

    if any(lower.startswith(p) for p in _POSTGRES):
        from .postgresql import PostgreSQLBackend

        return PostgreSQLBackend(effective_url)

    if any(lower.startswith(p) for p in _MYSQL):
        from .mysql import MySQLBackend

        return MySQLBackend(effective_url)

    # Default: SQLite — strip "sqlite:///" scheme prefix if present
    path = (
        effective_url[len("sqlite:///"):]
        if lower.startswith("sqlite:///")
        else effective_url
    )
    from .sqlite import SQLiteBackend

    return SQLiteBackend(path)


__all__ = ["DatabaseBackend", "DatabaseIntegrityError", "resolve_backend"]
