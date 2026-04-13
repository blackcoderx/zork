import os

import pytest

from zeno.db.connection import Database


@pytest.fixture
async def db(db_path):
    database = Database(db_path)
    await database.connect()
    yield database
    await database.disconnect()


@pytest.mark.asyncio
async def test_connect_creates_file(db, db_path):
    import os
    assert os.path.exists(db_path)


@pytest.mark.asyncio
async def test_execute_and_fetch(db):
    await db.execute("CREATE TABLE test (id TEXT, name TEXT)")
    await db.execute("INSERT INTO test (id, name) VALUES (?, ?)", ("1", "Alice"))
    row = await db.fetch_one("SELECT * FROM test WHERE id = ?", ("1",))
    assert row is not None
    assert row["id"] == "1"
    assert row["name"] == "Alice"


@pytest.mark.asyncio
async def test_fetch_all(db):
    await db.execute("CREATE TABLE items (id TEXT, val INTEGER)")
    await db.execute("INSERT INTO items (id, val) VALUES (?, ?)", ("a", 1))
    await db.execute("INSERT INTO items (id, val) VALUES (?, ?)", ("b", 2))
    rows = await db.fetch_all("SELECT * FROM items ORDER BY val")
    assert len(rows) == 2
    assert rows[0]["val"] == 1
    assert rows[1]["val"] == 2


@pytest.mark.asyncio
async def test_fetch_one_returns_none_when_missing(db):
    await db.execute("CREATE TABLE empty (id TEXT)")
    row = await db.fetch_one("SELECT * FROM empty WHERE id = ?", ("nope",))
    assert row is None


@pytest.mark.asyncio
async def test_foreign_keys_enabled(db):
    await db.execute("CREATE TABLE parent (id TEXT PRIMARY KEY)")
    await db.execute(
        "CREATE TABLE child (id TEXT, parent_id TEXT REFERENCES parent(id))"
    )
    await db.execute("INSERT INTO parent (id) VALUES ('p1')")
    await db.execute("INSERT INTO child (id, parent_id) VALUES ('c1', 'p1')")
    with pytest.raises(Exception):
        await db.execute("INSERT INTO child (id, parent_id) VALUES ('c2', 'nonexistent')")


# ---------------------------------------------------------------------------
# table_exists
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_table_exists_true(db):
    await db.execute("CREATE TABLE mytable (id TEXT)")
    assert await db.table_exists("mytable") is True


@pytest.mark.asyncio
async def test_table_exists_false(db):
    assert await db.table_exists("nonexistent_xyz_table") is False


# ---------------------------------------------------------------------------
# get_columns
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_columns_returns_name_key(db):
    await db.execute("CREATE TABLE cols (id TEXT, title TEXT, views INTEGER)")
    cols = await db.get_columns("cols")
    names = {c["name"] for c in cols}
    assert "id" in names
    assert "title" in names
    assert "views" in names


@pytest.mark.asyncio
async def test_get_columns_empty_after_no_table(db):
    # get_columns on a nonexistent table returns empty list (PRAGMA behaviour)
    cols = await db.get_columns("definitely_not_a_table")
    assert cols == []


# ---------------------------------------------------------------------------
# resolve_backend — dispatch logic (no real connections needed)
# ---------------------------------------------------------------------------

def test_resolve_backend_bare_path():
    from zeno.db.backends import resolve_backend
    from zeno.db.backends.sqlite import SQLiteBackend

    b = resolve_backend("app.db")
    assert isinstance(b, SQLiteBackend)


def test_resolve_backend_sqlite_url():
    from zeno.db.backends import resolve_backend
    from zeno.db.backends.sqlite import SQLiteBackend

    b = resolve_backend("sqlite:///data/app.db")
    assert isinstance(b, SQLiteBackend)
    assert b._path == "data/app.db"


def test_resolve_backend_postgres():
    from zeno.db.backends import resolve_backend
    from zeno.db.backends.postgresql import PostgreSQLBackend

    b = resolve_backend("postgresql://user:pass@localhost/db")
    assert isinstance(b, PostgreSQLBackend)


def test_resolve_backend_postgres_alias():
    from zeno.db.backends import resolve_backend
    from zeno.db.backends.postgresql import PostgreSQLBackend

    b = resolve_backend("postgres://user:pass@localhost/db")
    assert isinstance(b, PostgreSQLBackend)


def test_resolve_backend_mysql():
    from zeno.db.backends import resolve_backend
    from zeno.db.backends.mysql import MySQLBackend

    b = resolve_backend("mysql://user:pass@localhost/db")
    assert isinstance(b, MySQLBackend)


def test_resolve_backend_mysql_aiomysql_scheme():
    from zeno.db.backends import resolve_backend
    from zeno.db.backends.mysql import MySQLBackend

    b = resolve_backend("mysql+aiomysql://user:pass@localhost/db")
    assert isinstance(b, MySQLBackend)


# ---------------------------------------------------------------------------
# resolve_backend — env-var priority chain
# ---------------------------------------------------------------------------

def test_resolve_backend_env_zeno_database_url_overrides(monkeypatch):
    """ZENO_DATABASE_URL takes highest priority over all other sources."""
    from zeno.db.backends import resolve_backend
    from zeno.db.backends.sqlite import SQLiteBackend

    monkeypatch.setenv("ZENO_DATABASE_URL", "sqlite:///override.db")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    b = resolve_backend("postgresql://user:pass@localhost/db")  # ignored
    assert isinstance(b, SQLiteBackend)
    assert b._path == "override.db"


def test_resolve_backend_env_database_url_used_when_no_zeno_url(monkeypatch):
    """DATABASE_URL is used when ZENO_DATABASE_URL is not set."""
    from zeno.db.backends import resolve_backend
    from zeno.db.backends.sqlite import SQLiteBackend

    monkeypatch.delenv("ZENO_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///from_env.db")

    b = resolve_backend("app.db")  # ignored
    assert isinstance(b, SQLiteBackend)
    assert b._path == "from_env.db"


def test_resolve_backend_programmatic_value_used_when_no_env(monkeypatch):
    """Programmatic URL is used when no env vars are set."""
    from zeno.db.backends import resolve_backend
    from zeno.db.backends.sqlite import SQLiteBackend

    monkeypatch.delenv("ZENO_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    b = resolve_backend("sqlite:///programmatic.db")
    assert isinstance(b, SQLiteBackend)
    assert b._path == "programmatic.db"


def test_resolve_backend_zeno_url_beats_database_url(monkeypatch):
    """ZENO_DATABASE_URL beats DATABASE_URL when both are set."""
    from zeno.db.backends import resolve_backend
    from zeno.db.backends.postgresql import PostgreSQLBackend
    from zeno.db.backends.sqlite import SQLiteBackend

    monkeypatch.setenv("ZENO_DATABASE_URL", "postgresql://a:b@host/prod")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///dev.db")

    b = resolve_backend("app.db")  # ignored
    assert isinstance(b, PostgreSQLBackend)


# ---------------------------------------------------------------------------
# DatabaseIntegrityError exposed via Database shim
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_integrity_error_raised_on_unique_violation(db):
    from zeno.db.backends.base import DatabaseIntegrityError

    await db.execute("CREATE TABLE uniq (id TEXT PRIMARY KEY)")
    await db.execute("INSERT INTO uniq (id) VALUES (?)", ("dup",))
    with pytest.raises(DatabaseIntegrityError):
        await db.execute("INSERT INTO uniq (id) VALUES (?)", ("dup",))
