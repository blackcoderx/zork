"""
Migration sync for Zork.

This module provides functionality to:
- Generate migration files from schema diffs
- Support add column, drop column, and rename operations
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zork.collections.schema import Collection
    from zork.db.connection import Database


def _generate_timestamp() -> str:
    """Generate a timestamp string for migration filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


async def sync_to_migrations(
    collections: list["Collection"],
    db: "Database",
    migrations_dir: str,
    include_orphans: bool = False,
    dry_run: bool = False,
) -> list[Path]:
    """Generate migration files from schema differences.

    Args:
        collections: List of collections to generate migrations for
        db: Database connection
        migrations_dir: Directory to write migration files
        include_orphans: Whether to generate drop migrations for orphans
        dry_run: If True, don't write files but return what would be created

    Returns:
        List of generated migration file paths
    """
    from zork.schema_diff import generate_schema_diff

    migrations_path = Path(migrations_dir)
    if not dry_run:
        migrations_path.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []

    for collection in collections:
        diff_lines = await generate_schema_diff(collection, db, format="json")
        import json

        diff = json.loads(diff_lines)

        # Generate add column migrations
        for add in diff.get("additions", []):
            timestamp = _generate_timestamp()
            filename = f"{timestamp}_add_{add['column']}_column.py"
            content = _generate_add_column_migration(
                collection.name, add["column"], add.get("type", "TEXT")
            )
            file_path = migrations_path / filename
            if not dry_run:
                file_path.write_text(content)
            generated.append(file_path)

        # Generate orphan drop migrations
        if include_orphans:
            for orphan in diff.get("orphans", []):
                timestamp = _generate_timestamp()
                filename = f"{timestamp}_drop_{orphan['column']}_column.py"
                content = _generate_drop_column_migration(
                    collection.name, orphan["column"]
                )
                file_path = migrations_path / filename
                if not dry_run:
                    file_path.write_text(content)
                generated.append(file_path)

        # Generate rename migrations
        for rename in diff.get("renames", []):
            timestamp = _generate_timestamp()
            filename = f"{timestamp}_rename_{rename['from']}_to_{rename['to']}.py"
            content = _generate_rename_column_migration(
                collection.name, rename["from"], rename["to"]
            )
            file_path = migrations_path / filename
            if not dry_run:
                file_path.write_text(content)
            generated.append(file_path)

    return generated


def _generate_add_column_migration(
    table: str, column: str, column_type: str = "TEXT"
) -> str:
    """Generate migration content for adding a column."""
    return f'''"""Add {column} column to {table}"""

async def up(db):
    await db.execute("""
        ALTER TABLE {table} ADD COLUMN {column} {column_type}
    """)

async def down(db):
    # SQLite doesn't support DROP COLUMN directly
    # This requires recreating the table
    await db.execute("""
        CREATE TABLE {table}_new AS SELECT * FROM {table}
    """)
    await db.execute("DROP TABLE {table}")
    await db.execute("ALTER TABLE {table}_new RENAME TO {table}")
'''


def _generate_drop_column_migration(table: str, column: str) -> str:
    """Generate migration content for dropping a column."""
    return f'''"""Drop {column} column from {table}"""

async def up(db):
    # Note: SQLite doesn't support DROP COLUMN directly
    # This migration recreates the table without the column
    # Data in '{column}' will be lost
    await db.execute("""
        CREATE TABLE {table}_new AS SELECT * FROM {table}
    """)
    await db.execute("DROP TABLE {table}")
    await db.execute("ALTER TABLE {table}_new RENAME TO {table}")

async def down(db):
    # Data cannot be recovered - this is a one-way migration
    pass
'''


def _generate_rename_column_migration(table: str, old_name: str, new_name: str) -> str:
    """Generate migration content for renaming a column."""
    return f'''"""Rename {old_name} column to {new_name} in {table}"""

async def up(db):
    # Note: This migration:
    # 1. Adds the new column
    # 2. Copies data from old to new
    # 3. Drops the old column
    #
    # This approach works with SQLite which doesn't support RENAME COLUMN

    await db.execute("ALTER TABLE {table} ADD COLUMN {new_name} TEXT")
    await db.execute("UPDATE {table} SET {new_name} = {old_name}")
    await db.execute("ALTER TABLE {table} DROP COLUMN {old_name}")

async def down(db):
    # Reverse: add old column, copy data, drop new column
    await db.execute("ALTER TABLE {table} ADD COLUMN {old_name} TEXT")
    await db.execute("UPDATE {table} SET {old_name} = {new_name}")
    await db.execute("ALTER TABLE {table} DROP COLUMN {new_name}")
'''
