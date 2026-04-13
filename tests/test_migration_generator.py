import re
import pytest
from datetime import datetime, timezone
from zeno.collections.schema import Collection, TextField, IntField
from zeno.migrations.diff import AddTable, AddColumn, DropColumn
from zeno.migrations.generator import (
    generate_migration_id,
    generate_migration_content,
    write_migration_file,
)


# ---------------------------------------------------------------------------
# generate_migration_id
# ---------------------------------------------------------------------------

def test_generate_migration_id_format():
    mid = generate_migration_id("Add users table")
    assert re.match(r"^\d{8}_\d{6}_\w+$", mid)
    slug = mid.split("_", 2)[2]
    assert slug == slug.lower()
    assert " " not in slug
    assert "users" in slug
    assert "table" in slug


def test_generate_migration_id_special_chars():
    mid = generate_migration_id("Add index-posts")
    slug_part = mid.split("_", 2)[2]
    assert re.match(r"^[a-z0-9_]+$", slug_part)


# ---------------------------------------------------------------------------
# generate_migration_content — blank template
# ---------------------------------------------------------------------------

def test_blank_template_no_ops():
    content = generate_migration_content()
    assert "async def up(db):" in content
    assert "pass" in content
    assert "async def down(db):" in content


def test_blank_template_with_name():
    content = generate_migration_content(name="My migration step")
    assert "My migration step" in content
    assert "async def up(db):" in content


# ---------------------------------------------------------------------------
# generate_migration_content — specific operations
# ---------------------------------------------------------------------------

def test_add_column_op():
    ops = [AddColumn("posts", "category", "category TEXT")]
    content = generate_migration_content(ops)
    assert "ALTER TABLE posts ADD COLUMN category TEXT" in content
    assert "async def up(db):" in content
    assert "async def down(db):" in content
    # down should have a comment about DROP COLUMN
    assert "DROP COLUMN" in content


def test_add_table_op():
    collection = Collection("articles", fields=[TextField("title")])
    ops = [AddTable(collection)]
    content = generate_migration_content(ops)
    assert "CREATE TABLE" in content
    assert "articles" in content
    assert "DROP TABLE IF EXISTS articles" in content
    assert "async def up(db):" in content
    assert "async def down(db):" in content


def test_drop_column_op():
    ops = [DropColumn("posts", "old_col")]
    content = generate_migration_content(ops)
    assert "DESTRUCTIVE" in content
    assert "old_col" in content
    # up should have the DROP COLUMN as a comment
    up_section = content.split("async def up(db):")[1].split("async def down(db):")[0]
    assert "# " in up_section
    # down should mention restore from backup
    down_section = content.split("async def down(db):")[1]
    assert "backup" in down_section.lower() or "restore" in down_section.lower()


# ---------------------------------------------------------------------------
# write_migration_file
# ---------------------------------------------------------------------------

def test_write_migration_file_creates_dir(tmp_path):
    mig_dir = tmp_path / "mig"
    assert not mig_dir.exists()
    content = generate_migration_content(name="create dir test")
    write_migration_file(mig_dir, "create dir test", content)
    assert mig_dir.exists()
    assert mig_dir.is_dir()


def test_write_migration_file_returns_path(tmp_path):
    mig_dir = tmp_path / "migrations"
    content = generate_migration_content(name="test migration")
    path = write_migration_file(mig_dir, "test migration", content)
    assert path.exists()
    assert path.read_text(encoding="utf-8") == content


def test_write_migration_file_timestamp_in_name(tmp_path):
    mig_dir = tmp_path / "migrations"
    content = generate_migration_content()
    path = write_migration_file(mig_dir, "timestamp test", content)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    assert path.name.startswith(today)
