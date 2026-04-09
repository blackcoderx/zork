from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from cinder.db.connection import Database


class MigrationFile(NamedTuple):
    id: str       # filename stem (e.g. "20260409_143022_add_index")
    path: Path


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
        spec = importlib.util.spec_from_file_location(migration.id, migration.path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        await mod.up(self.db)
        applied_at = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "INSERT INTO _schema_migrations (id, applied_at) VALUES (?, ?)",
            (migration.id, applied_at),
        )

    async def rollback(self) -> MigrationFile | None:
        """Roll back the last applied migration. Returns the migration or None."""
        applied = await self.get_applied()
        if not applied:
            return None
        discovered = self.discover()
        # find the last applied migration in discovered order
        last = None
        for m in discovered:
            if m.id in applied:
                last = m
        if last is None:
            return None
        spec = importlib.util.spec_from_file_location(last.id, last.path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        await mod.down(self.db)
        await self.db.execute(
            "DELETE FROM _schema_migrations WHERE id = ?",
            (last.id,),
        )
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
        result = []
        for migration in self.discover():
            if migration.id in applied_map:
                result.append({
                    "id": migration.id,
                    "status": "applied",
                    "applied_at": applied_map[migration.id],
                })
            else:
                result.append({
                    "id": migration.id,
                    "status": "pending",
                    "applied_at": None,
                })
        return result
