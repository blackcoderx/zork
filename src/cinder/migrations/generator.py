import re
from datetime import datetime, timezone
from pathlib import Path
from .diff import AddTable, AddColumn, DropColumn


def generate_migration_id(name: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = name.lower().strip().replace(" ", "_").replace("-", "_")
    # remove non-alphanumeric chars except underscore
    slug = re.sub(r"[^a-z0-9_]", "_", slug)
    return f"{ts}_{slug}"


def generate_migration_content(operations: list | None = None, name: str = "") -> str:
    """Generate Python migration file content from a list of operations."""
    if not operations:
        return _blank_template(name)

    up_lines = []
    down_lines = []

    for op in operations:
        if isinstance(op, AddTable):
            sql = op.collection.build_create_table_sql().replace('"', '\\"')
            up_lines.append(f'    await db.execute("{sql}")')
            down_lines.append(f'    await db.execute("DROP TABLE IF EXISTS {op.collection.name}")')
        elif isinstance(op, AddColumn):
            up_lines.append(f'    await db.execute("ALTER TABLE {op.table} ADD COLUMN {op.col_sql}")')
            down_lines.append(f'    # DROP COLUMN not supported on SQLite < 3.35.0')
            down_lines.append(f'    # await db.execute("ALTER TABLE {op.table} DROP COLUMN {op.field_name}")')
        elif isinstance(op, DropColumn):
            up_lines.append(f'    # DESTRUCTIVE: uncomment to drop column {op.table}.{op.col_name}')
            up_lines.append(f'    # await db.execute("ALTER TABLE {op.table} DROP COLUMN {op.col_name}")')
            down_lines.append(f'    # Cannot restore dropped column {op.col_name} automatically - restore from backup')

    if not up_lines:
        up_lines = ["    pass"]
    if not down_lines:
        down_lines = ["    pass"]

    up_body = "\n".join(up_lines)
    down_body = "\n".join(down_lines)

    header = f'"""\n{name}\n"""\n\n' if name else ""

    return f'''{header}async def up(db):
{up_body}


async def down(db):
{down_body}
'''


def _blank_template(name: str = "") -> str:
    header = f'"""\n{name}\n"""\n\n' if name else ""
    return f'''{header}async def up(db):
    pass


async def down(db):
    pass
'''


def write_migration_file(migrations_dir: Path, name: str, content: str) -> Path:
    migrations_dir = Path(migrations_dir)
    migrations_dir.mkdir(parents=True, exist_ok=True)
    migration_id = generate_migration_id(name)
    filepath = migrations_dir / f"{migration_id}.py"
    filepath.write_text(content, encoding="utf-8")
    return filepath
