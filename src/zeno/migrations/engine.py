from __future__ import annotations

import importlib.util
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

_logger = logging.getLogger(__name__)

from cinder.db.connection import Database


class MigrationFile(NamedTuple):
    id: str       # filename stem (e.g. "20260409_143022_add_index")
    path: Path


def _load_migration_module(migration: MigrationFile):
    spec = importlib.util.spec_from_file_location(migration.id, migration.path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load migration file: {migration.path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class MigrationEngine:
    def __init__(self, db: Database, migrations_dir: str | Path = "migrations"):
        self.db = db
        self.migrations_dir = Path(migrations_dir)

    def discover(self) -> list[MigrationFile]:
        """Glob *.py in migrations_dir, sort by filename, skip files starting with _."""
        if not self.migrations_dir.exists():
            return []
        files = sorted(
            self.migrations_dir.glob("*.py"),
            key=lambda p: p.name,
        )
        return [
            MigrationFile(id=p.stem, path=p)
            for p in files
            if not p.name.startswith("_")
        ]

    async def ensure_table(self) -> None:
        """Create the _schema_migrations table if it doesn't exist."""
        await self.db.execute(
            "CREATE TABLE IF NOT EXISTS _schema_migrations "
            "(id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )

    async def get_applied(self) -> set[str]:
        """Return the set of applied migration IDs."""
        await self.ensure_table()
        rows = await self.db.fetch_all("SELECT id FROM _schema_migrations")
        return {row["id"] for row in rows}

    async def get_pending(self) -> list[MigrationFile]:
        """Return migrations that have not yet been applied."""
        applied = await self.get_applied()
        return [m for m in self.discover() if m.id not in applied]

    async def apply(self, migration: MigrationFile) -> None:
        """Load the migration module, call up(db), then record it as applied."""
        mod = _load_migration_module(migration)
        if not callable(getattr(mod, "up", None)):
            raise RuntimeError(f"Migration {migration.id!r} is missing an 'up' function: {migration.path}")
        # NOTE: DDL transactions are not natively abstracted by the Database interface.
        # If up() partially fails mid-migration, the schema may be left in an inconsistent
        # state. Migration authors should keep individual migration files atomic (single
        # DDL operation) where possible, or use compensating migrations to recover.
        try:
            await mod.up(self.db)
        except Exception as exc:
            raise RuntimeError(f"Migration {migration.id!r} failed during up(): {exc}") from exc
        applied_at = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "INSERT INTO _schema_migrations (id, applied_at) VALUES (?, ?)",
            (migration.id, applied_at),
        )

    async def rollback(self) -> "MigrationFile | None":
        """Roll back the last applied migration. Returns the migration or None."""
        await self.ensure_table()
        rows = await self.db.fetch_all(
            "SELECT id, applied_at FROM _schema_migrations ORDER BY applied_at DESC"
        )
        if not rows:
            return None
        last_id = rows[0]["id"]
        # Find the matching MigrationFile
        all_migrations = self.discover()
        last = next((m for m in all_migrations if m.id == last_id), None)
        if last is None:
            # File was deleted after being applied — remove orphaned record
            _logger.warning(
                "Migration %r was applied but its file no longer exists. "
                "Removing orphaned record from _schema_migrations. "
                "Verify your database schema manually.",
                last_id,
            )
            await self.db.execute("DELETE FROM _schema_migrations WHERE id = ?", (last_id,))
            return None
        mod = _load_migration_module(last)
        if not callable(getattr(mod, "down", None)):
            raise RuntimeError(f"Migration {last.id!r} is missing a 'down' function: {last.path}")
        try:
            await mod.down(self.db)
        except Exception as exc:
            raise RuntimeError(f"Migration {last.id!r} failed during down(): {exc}") from exc
        await self.db.execute("DELETE FROM _schema_migrations WHERE id = ?", (last.id,))
        return last

    async def run_pending(self) -> list[MigrationFile]:
        """Apply all pending migrations in order and return the list applied."""
        pending = await self.get_pending()
        for migration in pending:
            await self.apply(migration)
        return pending

    async def status(self) -> list[dict]:
        """Return all discovered migrations with their status and applied_at timestamp."""
        await self.ensure_table()
        rows = await self.db.fetch_all("SELECT id, applied_at FROM _schema_migrations")
        applied_map = {row["id"]: row["applied_at"] for row in rows}
        discovered_ids = set()
        result = []
        for m in self.discover():
            discovered_ids.add(m.id)
            if m.id in applied_map:
                result.append({"id": m.id, "status": "applied", "applied_at": applied_map[m.id]})
            else:
                result.append({"id": m.id, "status": "pending", "applied_at": None})
        # Surface orphaned migrations
        for mid, applied_at in applied_map.items():
            if mid not in discovered_ids:
                result.append({"id": mid, "status": "orphaned", "applied_at": applied_at})
        return result
