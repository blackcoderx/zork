"""
Schema diff generation for Zork.

This module provides functionality to:
- Compare collection schema against database schema
- Detect orphan columns (in DB but not in schema)
- Detect missing columns (in schema but not in DB)
- Detect potential typos (similar column names)
- Generate diff output in various formats
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from difflib import get_close_matches

from zork.collections.schema import Collection
from zork.db.connection import Database

logger = logging.getLogger("zork.schema_diff")


@dataclass
class SchemaDiff:
    """Represents the difference between a collection schema and database table."""

    collection: str
    additions: list[dict[str, str]]
    orphans: list[dict[str, str]]
    renames: list[dict[str, str]]  # Potential renames (typos)
    indexes: list[dict[str, str]]


def detect_typo(field_name: str, existing_names: set[str]) -> str | None:
    """Detect if field_name is similar to any existing column name.

    Uses difflib.get_close_matches with a high cutoff (0.8) to detect
    potential typos in column names.

    Args:
        field_name: The field name in the schema
        existing_names: Set of column names in the database

    Returns:
        The matching column name if found, None otherwise
    """
    if not existing_names:
        return None

    matches = get_close_matches(
        field_name.lower(),
        [name.lower() for name in existing_names],
        n=1,
        cutoff=0.8,
    )

    if matches:
        # Find the original cased name
        for name in existing_names:
            if name.lower() == matches[0]:
                return name
    return None


async def generate_schema_diff(
    collection: Collection,
    db: Database,
    format: str = "text",
) -> list[str] | str:
    """Generate a schema diff for a collection against its database table.

    Args:
        collection: The collection to compare
        db: The database connection
        format: Output format - "text" (default) or "json"

    Returns:
        List of diff lines (format="text") or JSON string (format="json")
    """
    table_name = collection.name

    # Get existing columns
    try:
        existing_cols = await db.get_columns(table_name)
    except Exception:
        # Table doesn't exist
        existing_cols = []

    existing_names = {col["name"] for col in existing_cols}
    schema_fields = {f.name for f in collection.fields}
    schema_fields.update({"id", "created_at", "updated_at"})

    additions: list[dict[str, str]] = []
    orphans: list[dict[str, str]] = []
    renames: list[dict[str, str]] = []
    indexes: list[dict[str, str]] = []

    # Find additions (in schema but not in DB)
    for field in collection.fields:
        if field.name not in existing_names:
            field_type = field.sqlite_type()
            additions.append({"column": field.name, "type": field_type})

            # Check for typo - is there an orphan similar to this?
            orphan_match = None
            for col_name in existing_names:
                if col_name not in schema_fields:
                    potential_orphan_match = detect_typo(col_name, {field.name})
                    if potential_orphan_match:
                        orphan_match = col_name
                        break

            if orphan_match:
                renames.append(
                    {
                        "from": orphan_match,
                        "to": field.name,
                        "suggestion": f"Possible typo: '{orphan_match}' looks like '{field.name}'",
                    }
                )

    # Find orphans (in DB but not in schema)
    for col_name in existing_names:
        if col_name not in schema_fields:
            # Get column type if available
            col_info = next((c for c in existing_cols if c["name"] == col_name), {})
            col_type = col_info.get("type", "TEXT")
            orphans.append(
                {
                    "column": col_name,
                    "type": col_type,
                    "warning": "Column in DB but not in schema",
                }
            )

    # Find new indexes
    existing_indexes = await db.get_indexes(table_name)
    existing_index_names = {idx["name"] for idx in existing_indexes}

    for idx_sql in collection.build_index_sqls():
        # Extract index name from SQL
        # Format: CREATE INDEX IF NOT EXISTS idx_name ON table (column)
        parts = idx_sql.split()
        if (
            len(parts) >= 6
            and parts[0].upper() == "CREATE"
            and parts[1].upper() == "INDEX"
        ):
            idx_name = parts[5]  # Index name is after "IF NOT EXISTS"
            if idx_name not in existing_index_names:
                indexes.append(
                    {
                        "name": idx_name,
                        "sql": idx_sql,
                    }
                )

    if format == "json":
        return json.dumps(
            {
                "collection": table_name,
                "additions": additions,
                "orphans": orphans,
                "renames": renames,
                "indexes": indexes,
            },
            indent=2,
        )

    # Text format
    lines: list[str] = []

    if additions or orphans or renames or indexes:
        lines.append(f"Collection: {table_name}")

    for add in additions:
        lines.append(f"  + Column: {add['column']} ({add['type']})")

    for rename in renames:
        lines.append(
            f"  ~ Possible typo: '{rename['from']}' looks like '{rename['to']}'"
        )

    for orphan in orphans:
        lines.append(f"  ! Orphan: {orphan['column']} ({orphan['type']})")

    for idx in indexes:
        lines.append(f"  + Index: {idx['name']}")

    return lines
