import pytest
from zeno.collections.schema import Collection, TextField, IntField
from zeno.migrations.diff import SchemaComparator, AddTable, AddColumn, DropColumn


# ---------------------------------------------------------------------------
# diff tests
# ---------------------------------------------------------------------------

async def test_diff_new_table(mem_db):
    collection = Collection("items", fields=[TextField("title")])
    comparator = SchemaComparator(mem_db, [collection])
    ops = await comparator.diff()
    assert len(ops) == 1
    assert isinstance(ops[0], AddTable)
    assert ops[0].collection is collection


async def test_diff_no_changes(mem_db):
    collection = Collection("items", fields=[TextField("title")])
    await mem_db.execute(
        "CREATE TABLE items (id TEXT PRIMARY KEY, title TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    comparator = SchemaComparator(mem_db, [collection])
    ops = await comparator.diff()
    assert ops == []


async def test_diff_new_column(mem_db):
    collection = Collection("items", fields=[TextField("title"), IntField("views")])
    # Create table without "views" column
    await mem_db.execute(
        "CREATE TABLE items (id TEXT PRIMARY KEY, title TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    comparator = SchemaComparator(mem_db, [collection])
    ops = await comparator.diff()
    assert len(ops) == 1
    assert isinstance(ops[0], AddColumn)
    assert ops[0].field_name == "views"
    assert ops[0].table == "items"


async def test_diff_drop_column(mem_db):
    collection = Collection("items", fields=[TextField("title")])
    # Create table with an extra column "extra_col"
    await mem_db.execute(
        "CREATE TABLE items ("
        "id TEXT PRIMARY KEY, title TEXT, extra_col TEXT, "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    comparator = SchemaComparator(mem_db, [collection])
    ops = await comparator.diff()
    assert len(ops) == 1
    assert isinstance(ops[0], DropColumn)
    assert ops[0].col_name == "extra_col"
    assert ops[0].destructive is True


async def test_diff_multiple_collections(mem_db):
    col1 = Collection("posts", fields=[TextField("title")])
    col2 = Collection("tags", fields=[TextField("label"), IntField("count")])
    # col1 (posts) table doesn't exist → AddTable
    # col2 (tags) table exists but missing "count" column → AddColumn
    await mem_db.execute(
        "CREATE TABLE tags (id TEXT PRIMARY KEY, label TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    comparator = SchemaComparator(mem_db, [col1, col2])
    ops = await comparator.diff()
    assert len(ops) == 2
    add_table_ops = [o for o in ops if isinstance(o, AddTable)]
    add_col_ops = [o for o in ops if isinstance(o, AddColumn)]
    assert len(add_table_ops) == 1
    assert add_table_ops[0].collection is col1
    assert len(add_col_ops) == 1
    assert add_col_ops[0].field_name == "count"


async def test_diff_builtin_columns_excluded(mem_db):
    collection = Collection("items", fields=[TextField("title")])
    # Create table with builtin columns id, created_at, updated_at — should not be DropColumn
    await mem_db.execute(
        "CREATE TABLE items ("
        "id TEXT PRIMARY KEY, title TEXT, "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    comparator = SchemaComparator(mem_db, [collection])
    ops = await comparator.diff()
    drop_ops = [o for o in ops if isinstance(o, DropColumn)]
    assert drop_ops == []
