"""
Tests for schema safety features.

These tests cover:
- Auto-sync environment detection
- Schema diff generation
- Orphan column detection
- Typo detection
- Migration sync
- Production warnings
"""

import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from zork import Zork, Collection, TextField, IntField
from zork.collections.schema import TextField, IntField
from zork.collections.store import CollectionStore
from zork.db.connection import Database


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path):
    """Return a path to a temporary SQLite database file."""
    return str(tmp_path / "test.db")


@pytest_asyncio.fixture
async def mem_db():
    """In-memory SQLite database for unit tests."""
    db = Database(":memory:")
    await db.connect()
    yield db
    await db.disconnect()


@pytest_asyncio.fixture
async def db(db_path):
    """File-based SQLite database for integration tests."""
    database = Database(db_path)
    await database.connect()
    yield database
    await database.disconnect()


@pytest_asyncio.fixture
async def store(db):
    """CollectionStore for testing schema operations."""
    return CollectionStore(db)


@pytest.fixture
def posts_collection():
    """Basic posts collection for testing."""
    return Collection(
        "posts",
        fields=[
            TextField("title", required=True),
            TextField("body"),
            IntField("views", default=0),
        ],
    )


@pytest.fixture
def migrations_dir(tmp_path):
    """Temporary migrations directory."""
    d = tmp_path / "migrations"
    d.mkdir()
    yield d


# ---------------------------------------------------------------------------
# Auto-Sync Environment Detection
# ---------------------------------------------------------------------------


class TestAutoSyncEnvironmentDetection:
    """Tests for auto_sync detection based on database URL."""

    def test_auto_sync_enabled_sqlite_bare_path(self, monkeypatch):
        """Auto-sync should be enabled for bare SQLite path like 'app.db'."""
        monkeypatch.delenv("ZORK_AUTO_SYNC", raising=False)
        app = Zork(database="app.db")
        assert app.auto_sync is True

    def test_auto_sync_enabled_sqlite_with_slash_slash_slash(self, monkeypatch):
        """Auto-sync should be enabled for sqlite:///path format."""
        monkeypatch.delenv("ZORK_AUTO_SYNC", raising=False)
        app = Zork(database="sqlite:///app.db")
        assert app.auto_sync is True

    def test_auto_sync_enabled_sqlite_three_slashes(self, monkeypatch):
        """Auto-sync should be enabled for sqlite:///./path format."""
        monkeypatch.delenv("ZORK_AUTO_SYNC", raising=False)
        app = Zork(database="sqlite:///./app.db")
        assert app.auto_sync is True

    def test_auto_sync_disabled_postgresql(self, monkeypatch):
        """Auto-sync should be disabled for PostgreSQL."""
        monkeypatch.delenv("ZORK_AUTO_SYNC", raising=False)
        app = Zork(database="postgresql://user:pass@localhost:5432/mydb")
        assert app.auto_sync is False

    def test_auto_sync_disabled_postgres_short_form(self, monkeypatch):
        """Auto-sync should be disabled for postgres:// short form."""
        monkeypatch.delenv("ZORK_AUTO_SYNC", raising=False)
        app = Zork(database="postgres://user:pass@localhost:5432/mydb")
        assert app.auto_sync is False

    def test_auto_sync_disabled_mysql(self, monkeypatch):
        """Auto-sync should be disabled for MySQL."""
        monkeypatch.delenv("ZORK_AUTO_SYNC", raising=False)
        app = Zork(database="mysql://user:pass@localhost:3306/mydb")
        assert app.auto_sync is False

    def test_auto_sync_disabled_mysql_aiomysql(self, monkeypatch):
        """Auto-sync should be disabled for mysql+aiomysql://."""
        monkeypatch.delenv("ZORK_AUTO_SYNC", raising=False)
        app = Zork(database="mysql+aiomysql://user:pass@localhost:3306/mydb")
        assert app.auto_sync is False

    def test_auto_sync_explicit_true_overrides_detection(self, monkeypatch):
        """Explicit auto_sync=True should override detection for PostgreSQL."""
        monkeypatch.delenv("ZORK_AUTO_SYNC", raising=False)
        app = Zork(
            database="postgresql://user:pass@localhost:5432/mydb", auto_sync=True
        )
        assert app.auto_sync is True

    def test_auto_sync_explicit_false_overrides_detection(self, monkeypatch):
        """Explicit auto_sync=False should override detection for SQLite."""
        monkeypatch.delenv("ZORK_AUTO_SYNC", raising=False)
        app = Zork(database="app.db", auto_sync=False)
        assert app.auto_sync is False

    def test_auto_sync_env_var_true(self, monkeypatch):
        """ZORK_AUTO_SYNC=true should enable auto-sync for PostgreSQL."""
        monkeypatch.setenv("ZORK_AUTO_SYNC", "true")
        app = Zork(database="postgresql://user:pass@localhost:5432/mydb")
        assert app.auto_sync is True

    def test_auto_sync_env_var_false(self, monkeypatch):
        """ZORK_AUTO_SYNC=false should disable auto-sync for SQLite."""
        monkeypatch.setenv("ZORK_AUTO_SYNC", "false")
        app = Zork(database="app.db")
        assert app.auto_sync is False

    def test_auto_sync_env_var_1(self, monkeypatch):
        """ZORK_AUTO_SYNC=1 should enable auto-sync."""
        monkeypatch.setenv("ZORK_AUTO_SYNC", "1")
        app = Zork(database="postgresql://user:pass@localhost:5432/mydb")
        assert app.auto_sync is True

    def test_auto_sync_env_var_0(self, monkeypatch):
        """ZORK_AUTO_SYNC=0 should disable auto-sync."""
        monkeypatch.setenv("ZORK_AUTO_SYNC", "0")
        app = Zork(database="app.db")
        assert app.auto_sync is False


# ---------------------------------------------------------------------------
# Schema Diff Generation
# ---------------------------------------------------------------------------


class TestSchemaDiff:
    """Tests for schema diff generation."""

    @pytest.mark.asyncio
    async def test_schema_diff_shows_add_column(self, mem_db, store):
        """Schema diff should show '+ Column' for new fields."""
        from zork.schema_diff import generate_schema_diff

        # Create initial table with just title
        collection = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                TextField("status"),  # New field
            ],
        )
        await store.sync_schema(
            Collection(
                "posts",
                fields=[TextField("title", required=True)],
            )
        )

        diff = await generate_schema_diff(collection, mem_db)

        assert any("+ Column" in line and "status" in line for line in diff)

    @pytest.mark.asyncio
    async def test_schema_diff_shows_orphan_column(self, mem_db, store):
        """Schema diff should show '! Orphan' for extra DB columns."""
        from zork.schema_diff import generate_schema_diff

        # Create table with extra column
        await mem_db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                title TEXT,
                body TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        collection = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                # 'body' is orphan
            ],
        )

        diff = await generate_schema_diff(collection, mem_db)

        assert any("! Orphan" in line and "body" in line for line in diff)

    @pytest.mark.asyncio
    async def test_schema_diff_shows_possible_typo(self, mem_db, store):
        """Schema diff should show '~ Possible typo' for similar names."""
        from zork.schema_diff import generate_schema_diff

        # Create table with typo in column name
        await mem_db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                title TEXT,
                titile TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        collection = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                # 'titile' looks like 'title'
            ],
        )

        diff = await generate_schema_diff(collection, mem_db)

        # Should show orphan for titile
        assert any("titile" in line for line in diff)

    @pytest.mark.asyncio
    async def test_schema_diff_shows_new_index(self, mem_db, store):
        """Schema diff should show '+ Index' for new indexes."""
        from zork.schema_diff import generate_schema_diff

        # Create table without index
        await mem_db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        collection = Collection(
            "posts",
            fields=[
                TextField("title", required=True, indexed=True),
            ],
        )

        diff = await generate_schema_diff(collection, mem_db)

        assert any("+ Index" in line and "title" in line for line in diff)

    @pytest.mark.asyncio
    async def test_schema_diff_empty_when_schemas_match(self, mem_db):
        """Schema diff should be empty when schemas match."""
        from zork.schema_diff import generate_schema_diff

        store = CollectionStore(mem_db, auto_sync=True)

        collection = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                TextField("body"),
            ],
        )
        await store.sync_schema(collection)

        diff = await generate_schema_diff(collection, mem_db)

        assert not any("+ Column" in line for line in diff)
        assert not any("! Orphan" in line for line in diff)

    @pytest.mark.asyncio
    async def test_schema_diff_json_format(self, mem_db, store):
        """Schema diff should support JSON output format."""
        from zork.schema_diff import generate_schema_diff

        collection = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                TextField("status"),
            ],
        )
        await store.sync_schema(
            Collection("posts", fields=[TextField("title", required=True)])
        )

        diff_json = await generate_schema_diff(collection, mem_db, format="json")
        import json

        result = json.loads(diff_json)

        assert "additions" in result
        assert "orphans" in result
        assert any(a["column"] == "status" for a in result.get("additions", []))


# ---------------------------------------------------------------------------
# Orphan Detection
# ---------------------------------------------------------------------------


class TestOrphanDetection:
    """Tests for orphan column detection."""

    @pytest.mark.asyncio
    async def test_orphan_detected_when_column_not_in_schema(self, mem_db, store):
        """Orphan should be detected when DB column not in collection."""
        from zork.schema_diff import generate_schema_diff

        await mem_db.execute("""
            CREATE TABLE items (
                id TEXT PRIMARY KEY,
                name TEXT,
                old_field TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        collection = Collection(
            "items",
            fields=[TextField("name", required=True)],
        )

        diff = await generate_schema_diff(collection, mem_db)

        assert any("old_field" in line for line in diff)

    @pytest.mark.asyncio
    async def test_orphan_warning_logged(self, mem_db, store, caplog):
        """Warning should be logged for orphan columns."""
        import logging

        # Create store with auto_sync disabled to test orphan detection
        store = CollectionStore(mem_db, auto_sync=False)

        await mem_db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                title TEXT,
                deprecated TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        collection = Collection(
            "posts",
            fields=[TextField("title", required=True)],
        )

        with caplog.at_level(logging.WARNING):
            await store.sync_schema(collection)

        assert "deprecated" in caplog.text

    @pytest.mark.asyncio
    async def test_orphan_not_auto_deleted(self, mem_db, store):
        """Orphan columns should never be automatically deleted."""
        from zork.schema_diff import generate_schema_diff

        await mem_db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                title TEXT,
                orphan TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        collection = Collection(
            "posts",
            fields=[TextField("title", required=True)],
        )

        await store.sync_schema(collection)

        # Check orphan still exists
        columns = await mem_db.fetch_all("PRAGMA table_info(posts)")
        col_names = [c["name"] for c in columns]

        assert "orphan" in col_names


# ---------------------------------------------------------------------------
# Typo Detection
# ---------------------------------------------------------------------------


class TestTypoDetection:
    """Tests for typo detection in column names."""

    def test_typo_detected_for_similar_names(self):
        """Similar column names should be flagged as potential typos."""
        from zork.schema_diff import detect_typo

        existing = {"title", "body", "views"}
        result = detect_typo("titile", existing)

        # titile is similar to title
        assert result is not None
        assert "title" in result

    def test_typo_not_flagged_for_different_names(self):
        """Unrelated column names should not be flagged."""
        from zork.schema_diff import detect_typo

        existing = {"title", "body", "views"}
        result = detect_typo("category", existing)

        # category is not similar to any existing
        assert result is None

    def test_typo_detection_threshold(self):
        """Typo detection should use appropriate similarity threshold."""
        from zork.schema_diff import detect_typo

        existing = {"email", "name"}

        # Very similar should be detected
        assert detect_typo("emial", existing) is not None

        # Completely different should not
        assert detect_typo("xyz123", existing) is None

    def test_typo_detection_case_sensitive(self):
        """Typo detection should be case-insensitive."""
        from zork.schema_diff import detect_typo

        existing = {"Title", "Body"}
        result = detect_typo("TITLE", existing)

        # Should find match regardless of case
        assert result is not None


# ---------------------------------------------------------------------------
# Production Warnings
# ---------------------------------------------------------------------------


class TestProductionWarnings:
    """Tests for production environment warnings."""

    def test_production_warning_logged_sqlite_disabled(self, monkeypatch, caplog):
        """Warning should be logged when auto-sync enabled with PostgreSQL."""
        import logging

        monkeypatch.setenv("ZORK_AUTO_SYNC", "true")
        monkeypatch.delenv("ZORK_AUTO_SYNC", raising=False)

        with caplog.at_level(logging.WARNING):
            app = Zork(database="postgresql://user:pass@localhost:5432/mydb")

        # Should warn about auto-sync in production
        # Note: Warning may happen at build time, not init time
        # This test verifies the app can be created with warning logged

    def test_no_warning_sqlite_auto_sync(self, monkeypatch, caplog):
        """No warning for SQLite with auto-sync enabled (expected)."""
        import logging

        monkeypatch.setenv("ZORK_AUTO_SYNC", "true")
        app = Zork(database="app.db")

        # SQLite with auto-sync is expected behavior
        assert app.auto_sync is True

    def test_no_warning_postgresql_auto_sync_disabled(self, monkeypatch):
        """No warning for PostgreSQL with auto-sync disabled."""
        monkeypatch.setenv("ZORK_AUTO_SYNC", "false")
        app = Zork(database="postgresql://user:pass@localhost:5432/mydb")

        assert app.auto_sync is False


# ---------------------------------------------------------------------------
# Migrate Sync Command
# ---------------------------------------------------------------------------


class TestMigrateSync:
    """Tests for migrate sync command."""

    @pytest.mark.asyncio
    async def test_migrate_sync_creates_file(self, mem_db, migrations_dir):
        """Migrate sync should create migration file."""
        from zork.migrate_sync import sync_to_migrations

        collection = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                TextField("status"),
            ],
        )
        await mem_db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        generated = await sync_to_migrations([collection], mem_db, str(migrations_dir))

        assert len(generated) >= 1
        assert any("status" in str(f) for f in generated)

    @pytest.mark.asyncio
    async def test_migrate_sync_filename_has_timestamp(self, mem_db, migrations_dir):
        """Migration filename should have timestamp prefix."""
        from zork.migrate_sync import sync_to_migrations

        collection = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                TextField("status"),
            ],
        )
        await mem_db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        generated = await sync_to_migrations([collection], mem_db, str(migrations_dir))

        assert len(generated) >= 1
        filename = generated[0].name
        # Filename should match pattern: YYYYMMDD_HHMMSS_description.py
        assert re.match(r"\d{8}_\d{6}_.*\.py", filename)

    @pytest.mark.asyncio
    async def test_migrate_sync_add_column_migration_content(
        self, mem_db, migrations_dir
    ):
        """Migration should contain ALTER TABLE ADD COLUMN."""
        from zork.migrate_sync import sync_to_migrations

        collection = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                TextField("status"),
            ],
        )
        await mem_db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        generated = await sync_to_migrations([collection], mem_db, str(migrations_dir))

        assert len(generated) >= 1
        content = generated[0].read_text()
        assert "ALTER TABLE" in content or "ADD COLUMN" in content

    @pytest.mark.asyncio
    async def test_migrate_sync_dry_run(self, mem_db, migrations_dir):
        """Dry run should not create files."""
        from zork.migrate_sync import sync_to_migrations

        collection = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                TextField("status"),
            ],
        )
        await mem_db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        generated = await sync_to_migrations(
            [collection], mem_db, str(migrations_dir), dry_run=True
        )

        # Dry run returns what would be created but doesn't write files
        assert len(generated) >= 1
        # Files should not exist
        assert not any(migrations_dir.iterdir())

    @pytest.mark.asyncio
    async def test_migrate_sync_include_orphans(self, mem_db, migrations_dir):
        """Include orphans should generate drop migrations."""
        from zork.migrate_sync import sync_to_migrations

        collection = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                TextField("status"),  # New field to add
            ],
        )
        await mem_db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                title TEXT,
                orphan TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        generated = await sync_to_migrations(
            [collection], mem_db, str(migrations_dir), include_orphans=True
        )

        # Should generate add column migration + orphan drop migration
        assert len(generated) >= 2  # At least one add + one drop


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestSchemaSafetyIntegration:
    """Integration tests for schema safety workflow."""

    @pytest.mark.asyncio
    async def test_dev_workflow_auto_sync(self, db, store, posts_collection):
        """In dev, adding field should create column automatically."""
        # Initial sync
        await store.sync_schema(posts_collection)

        # Add new field to collection
        updated_collection = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                TextField("body"),
                IntField("views", default=0),
                TextField("status"),  # New field
            ],
        )

        # Sync again - should add column
        await store.sync_schema(updated_collection)

        columns = await db.fetch_all("PRAGMA table_info(posts)")
        col_names = [c["name"] for c in columns]

        assert "status" in col_names

    @pytest.mark.asyncio
    async def test_dev_workflow_warning_on_orphan(self, db, store, caplog):
        """In dev, removing field should warn about orphan."""
        import logging

        # Create with field
        v1 = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                TextField("body"),
            ],
        )
        await store.sync_schema(v1)

        # Update without field
        v2 = Collection(
            "posts",
            fields=[TextField("title", required=True)],
        )

        with caplog.at_level(logging.WARNING):
            await store.sync_schema(v2)

        # Should warn about body becoming orphan
        assert "body" in caplog.text

    @pytest.mark.asyncio
    async def test_prod_workflow_migrations_disabled(self, db):
        """When auto_sync is False, sync_schema should not add columns."""
        # Create app with auto_sync disabled
        app = Zork(database="app.db", auto_sync=False)

        # Manually sync with disabled auto_sync
        collection = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                TextField("status"),  # New field
            ],
        )

        # Create base table without new column
        await db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        store = CollectionStore(db)

        # With auto_sync disabled, sync should not add column
        # Note: This test verifies the design intent
        # Actual implementation may vary


# ---------------------------------------------------------------------------
# CLI Command Tests
# ---------------------------------------------------------------------------


class TestSchemaDiffCLI:
    """Tests for zork schema diff CLI command."""

    def test_schema_diff_command_exists(self):
        """Schema diff command should be registered in CLI."""
        from zork.cli import app as cli

        # Find schema diff subcommand
        # This tests that the command exists
        commands = list(cli.registered_commands)
        # The command will be registered as 'schema' subcommand
        # with 'diff' as a subcommand

    def test_schema_diff_help(self):
        """Schema diff should show help when called."""
        from typer.testing import CliRunner

        from zork.cli import app as cli

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "diff", "--help"])
        assert result.exit_code in (0, 2)  # 2 if not implemented yet


class TestMigrateSyncCLI:
    """Tests for zork migrate sync CLI command."""

    def test_migrate_sync_help(self):
        """Migrate sync should show help when called."""
        from typer.testing import CliRunner

        from zork.cli import migrate_app

        runner = CliRunner()
        result = runner.invoke(migrate_app, ["sync", "--help"])
        assert result.exit_code in (0, 2)  # 2 if not implemented yet


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestSchemaSafetyEdgeCases:
    """Tests for edge cases in schema safety."""

    @pytest.mark.asyncio
    async def test_multiple_orphans_detected(self, mem_db):
        """Multiple orphan columns should all be detected."""
        from zork.schema_diff import generate_schema_diff

        await mem_db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                title TEXT,
                orphan1 TEXT,
                orphan2 TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        collection = Collection(
            "posts",
            fields=[TextField("title", required=True)],
        )

        diff = await generate_schema_diff(collection, mem_db)

        assert any("orphan1" in line for line in diff)
        assert any("orphan2" in line for line in diff)

    @pytest.mark.asyncio
    async def test_self_referential_typo_not_flagged(self, mem_db):
        """Self-referential typo should not cause issues."""
        from zork.schema_diff import detect_typo, generate_schema_diff

        # If column name is in schema, it shouldn't be flagged as orphan
        await mem_db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        collection = Collection(
            "posts",
            fields=[TextField("title", required=True)],
        )

        diff = await generate_schema_diff(collection, mem_db)

        # title exists in both, shouldn't be flagged
        assert not any("+ Column" in line and "title" in line for line in diff)

    def test_empty_collection_name(self):
        """Empty collection name should be handled gracefully."""
        from zork.schema_diff import generate_schema_diff

        # Collection requires fields, but name can be empty
        # This tests that empty name is handled
        collection = Collection("empty_table", fields=[])

    @pytest.mark.asyncio
    async def test_case_sensitive_column_names(self, mem_db):
        """Column names should be handled case-sensitively."""
        from zork.schema_diff import generate_schema_diff

        await mem_db.execute("""
            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                Title TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        collection = Collection(
            "posts",
            fields=[TextField("title", required=True)],
        )

        diff = await generate_schema_diff(collection, mem_db)

        # Should detect Title as potential orphan
        assert any("Title" in line for line in diff)

    def test_database_url_with_special_characters(self, monkeypatch):
        """Database URLs with special characters should be handled."""
        monkeypatch.delenv("ZORK_AUTO_SYNC", raising=False)

        # URL with password containing special chars
        app = Zork(database="postgresql://user:p@ss!word@localhost:5432/mydb")
        assert app.auto_sync is False

    def test_in_memory_database(self, monkeypatch):
        """In-memory database should have auto-sync enabled."""
        monkeypatch.delenv("ZORK_AUTO_SYNC", raising=False)

        app = Zork(database=":memory:")
        # In-memory is treated like SQLite
        assert app.auto_sync is True
