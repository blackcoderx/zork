import pytest
from pathlib import Path
from cinder.db.connection import Database
from cinder.migrations.engine import MigrationEngine, MigrationFile


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.disconnect()


@pytest.fixture
def migrations_dir(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    yield d


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------

async def test_discover_empty(db, migrations_dir):
    engine = MigrationEngine(db, migrations_dir)
    assert engine.discover() == []


async def test_discover_sorted(db, migrations_dir):
    (migrations_dir / "20260409_120000_alpha.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    (migrations_dir / "20260409_130000_bravo.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    (migrations_dir / "20260409_140000_charlie.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(db, migrations_dir)
    found = engine.discover()
    assert [m.id for m in found] == [
        "20260409_120000_alpha",
        "20260409_130000_bravo",
        "20260409_140000_charlie",
    ]


async def test_discover_skips_underscore_files(db, migrations_dir):
    (migrations_dir / "__init__.py").write_text("")
    (migrations_dir / "_helpers.py").write_text("")
    (migrations_dir / "20260409_100000_real.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(db, migrations_dir)
    found = engine.discover()
    assert len(found) == 1
    assert found[0].id == "20260409_100000_real"


# ---------------------------------------------------------------------------
# ensure_table / get_applied
# ---------------------------------------------------------------------------

async def test_ensure_table_creates_table(db, migrations_dir):
    engine = MigrationEngine(db, migrations_dir)
    await engine.ensure_table()
    assert await db.table_exists("_schema_migrations") is True


async def test_get_applied_empty(db, migrations_dir):
    engine = MigrationEngine(db, migrations_dir)
    applied = await engine.get_applied()
    assert applied == set()


# ---------------------------------------------------------------------------
# get_pending
# ---------------------------------------------------------------------------

async def test_get_pending_all_when_none_applied(db, migrations_dir):
    (migrations_dir / "20260409_100000_first.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(db, migrations_dir)
    pending = await engine.get_pending()
    assert len(pending) == 1
    assert pending[0].id == "20260409_100000_first"


async def test_get_pending_filters_applied(db, migrations_dir):
    (migrations_dir / "20260409_100000_first.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    (migrations_dir / "20260409_110000_second.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(db, migrations_dir)
    await engine.ensure_table()
    await db.execute(
        "INSERT INTO _schema_migrations (id, applied_at) VALUES (?, ?)",
        ("20260409_100000_first", "2026-04-09T10:00:00+00:00"),
    )
    pending = await engine.get_pending()
    assert len(pending) == 1
    assert pending[0].id == "20260409_110000_second"


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

async def test_apply_calls_up_and_records(db, migrations_dir):
    mig_file = migrations_dir / "20260409_100000_create_test.py"
    mig_file.write_text(
        "async def up(db):\n"
        "    await db.execute('CREATE TABLE test_apply (x INTEGER)')\n"
        "\n"
        "async def down(db):\n"
        "    await db.execute('DROP TABLE IF EXISTS test_apply')\n"
    )
    engine = MigrationEngine(db, migrations_dir)
    await engine.ensure_table()
    mig = MigrationFile(id=mig_file.stem, path=mig_file)
    await engine.apply(mig)
    assert await db.table_exists("test_apply") is True
    row = await db.fetch_one("SELECT id FROM _schema_migrations WHERE id = ?", (mig_file.stem,))
    assert row is not None


async def test_apply_wraps_errors(db, migrations_dir):
    mig_file = migrations_dir / "20260409_200000_bad.py"
    mig_file.write_text(
        "async def up(db):\n"
        "    raise RuntimeError('boom')\n"
        "\n"
        "async def down(db):\n"
        "    pass\n"
    )
    engine = MigrationEngine(db, migrations_dir)
    await engine.ensure_table()
    mig = MigrationFile(id=mig_file.stem, path=mig_file)
    with pytest.raises(RuntimeError, match="20260409_200000_bad"):
        await engine.apply(mig)


async def test_apply_validates_up_function(db, migrations_dir):
    mig_file = migrations_dir / "20260409_300000_no_up.py"
    mig_file.write_text("x = 1\n")
    engine = MigrationEngine(db, migrations_dir)
    await engine.ensure_table()
    mig = MigrationFile(id=mig_file.stem, path=mig_file)
    with pytest.raises(RuntimeError):
        await engine.apply(mig)


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------

async def test_rollback_calls_down_and_removes_record(db, migrations_dir):
    mig_file = migrations_dir / "20260409_100000_create_rb.py"
    mig_file.write_text(
        "async def up(db):\n"
        "    await db.execute('CREATE TABLE rb_table (x INTEGER)')\n"
        "\n"
        "async def down(db):\n"
        "    await db.execute('DROP TABLE IF EXISTS rb_table')\n"
    )
    engine = MigrationEngine(db, migrations_dir)
    await engine.ensure_table()
    mig = MigrationFile(id=mig_file.stem, path=mig_file)
    await engine.apply(mig)
    assert await db.table_exists("rb_table") is True

    result = await engine.rollback()
    assert result is not None
    assert result.id == mig_file.stem
    assert await db.table_exists("rb_table") is False
    row = await db.fetch_one("SELECT id FROM _schema_migrations WHERE id = ?", (mig_file.stem,))
    assert row is None


async def test_rollback_returns_none_when_nothing_applied(db, migrations_dir):
    engine = MigrationEngine(db, migrations_dir)
    result = await engine.rollback()
    assert result is None


async def test_rollback_uses_applied_at_order(db, migrations_dir):
    mig1 = migrations_dir / "20260409_100000_first.py"
    mig1.write_text(
        "async def up(db):\n"
        "    await db.execute('CREATE TABLE rb_first (x INTEGER)')\n"
        "\n"
        "async def down(db):\n"
        "    await db.execute('DROP TABLE IF EXISTS rb_first')\n"
    )
    mig2 = migrations_dir / "20260409_110000_second.py"
    mig2.write_text(
        "async def up(db):\n"
        "    await db.execute('CREATE TABLE rb_second (x INTEGER)')\n"
        "\n"
        "async def down(db):\n"
        "    await db.execute('DROP TABLE IF EXISTS rb_second')\n"
    )
    engine = MigrationEngine(db, migrations_dir)
    await engine.ensure_table()
    await engine.apply(MigrationFile(id=mig1.stem, path=mig1))
    await engine.apply(MigrationFile(id=mig2.stem, path=mig2))

    result = await engine.rollback()
    assert result is not None
    assert result.id == mig2.stem
    assert await db.table_exists("rb_second") is False
    assert await db.table_exists("rb_first") is True


# ---------------------------------------------------------------------------
# run_pending
# ---------------------------------------------------------------------------

async def test_run_pending_multiple(db, migrations_dir):
    for i in range(1, 4):
        f = migrations_dir / f"20260409_1{i}0000_mig{i}.py"
        f.write_text(
            f"async def up(db):\n"
            f"    await db.execute('CREATE TABLE run_pending_{i} (x INTEGER)')\n"
            f"\n"
            f"async def down(db):\n"
            f"    await db.execute('DROP TABLE IF EXISTS run_pending_{i}')\n"
        )
    engine = MigrationEngine(db, migrations_dir)
    applied = await engine.run_pending()
    assert len(applied) == 3
    for i in range(1, 4):
        assert await db.table_exists(f"run_pending_{i}") is True


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

async def test_status_all_pending(db, migrations_dir):
    (migrations_dir / "20260409_100000_a.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    (migrations_dir / "20260409_110000_b.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(db, migrations_dir)
    statuses = await engine.status()
    assert len(statuses) == 2
    assert all(s["status"] == "pending" for s in statuses)


async def test_status_mixed(db, migrations_dir):
    mig1 = migrations_dir / "20260409_100000_done.py"
    mig1.write_text("async def up(db): pass\nasync def down(db): pass\n")
    mig2 = migrations_dir / "20260409_110000_todo.py"
    mig2.write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(db, migrations_dir)
    await engine.ensure_table()
    await db.execute(
        "INSERT INTO _schema_migrations (id, applied_at) VALUES (?, ?)",
        ("20260409_100000_done", "2026-04-09T10:00:00+00:00"),
    )
    statuses = await engine.status()
    by_id = {s["id"]: s for s in statuses}
    assert by_id["20260409_100000_done"]["status"] == "applied"
    assert by_id["20260409_110000_todo"]["status"] == "pending"


async def test_status_orphaned(db, migrations_dir):
    mig_file = migrations_dir / "20260409_100000_orphan.py"
    mig_file.write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(db, migrations_dir)
    await engine.ensure_table()
    await db.execute(
        "INSERT INTO _schema_migrations (id, applied_at) VALUES (?, ?)",
        ("20260409_100000_orphan", "2026-04-09T10:00:00+00:00"),
    )
    # Delete the file to simulate orphan
    mig_file.unlink()
    statuses = await engine.status()
    orphaned = [s for s in statuses if s["status"] == "orphaned"]
    assert len(orphaned) == 1
    assert orphaned[0]["id"] == "20260409_100000_orphan"
