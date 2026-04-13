import pytest
from pathlib import Path
from zeno.migrations.engine import MigrationEngine, MigrationFile


@pytest.fixture
def migrations_dir(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    yield d


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------

async def test_discover_empty(mem_db, migrations_dir):
    engine = MigrationEngine(mem_db, migrations_dir)
    assert engine.discover() == []


async def test_discover_sorted(mem_db, migrations_dir):
    (migrations_dir / "20260409_120000_alpha.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    (migrations_dir / "20260409_130000_bravo.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    (migrations_dir / "20260409_140000_charlie.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(mem_db, migrations_dir)
    found = engine.discover()
    assert [m.id for m in found] == [
        "20260409_120000_alpha",
        "20260409_130000_bravo",
        "20260409_140000_charlie",
    ]


async def test_discover_skips_underscore_files(mem_db, migrations_dir):
    (migrations_dir / "__init__.py").write_text("")
    (migrations_dir / "_helpers.py").write_text("")
    (migrations_dir / "20260409_100000_real.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(mem_db, migrations_dir)
    found = engine.discover()
    assert len(found) == 1
    assert found[0].id == "20260409_100000_real"


# ---------------------------------------------------------------------------
# ensure_table / get_applied
# ---------------------------------------------------------------------------

async def test_ensure_table_creates_table(mem_db, migrations_dir):
    engine = MigrationEngine(mem_db, migrations_dir)
    await engine.ensure_table()
    assert await mem_db.table_exists("_schema_migrations") is True


async def test_get_applied_empty(mem_db, migrations_dir):
    engine = MigrationEngine(mem_db, migrations_dir)
    applied = await engine.get_applied()
    assert applied == set()


# ---------------------------------------------------------------------------
# get_pending
# ---------------------------------------------------------------------------

async def test_get_pending_all_when_none_applied(mem_db, migrations_dir):
    (migrations_dir / "20260409_100000_first.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(mem_db, migrations_dir)
    pending = await engine.get_pending()
    assert len(pending) == 1
    assert pending[0].id == "20260409_100000_first"


async def test_get_pending_filters_applied(mem_db, migrations_dir):
    (migrations_dir / "20260409_100000_first.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    (migrations_dir / "20260409_110000_second.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(mem_db, migrations_dir)
    await engine.ensure_table()
    await mem_db.execute(
        "INSERT INTO _schema_migrations (id, applied_at) VALUES (?, ?)",
        ("20260409_100000_first", "2026-04-09T10:00:00+00:00"),
    )
    pending = await engine.get_pending()
    assert len(pending) == 1
    assert pending[0].id == "20260409_110000_second"


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

async def test_apply_calls_up_and_records(mem_db, migrations_dir):
    mig_file = migrations_dir / "20260409_100000_create_test.py"
    mig_file.write_text(
        "async def up(db):\n"
        "    await db.execute('CREATE TABLE test_apply (x INTEGER)')\n"
        "\n"
        "async def down(db):\n"
        "    await db.execute('DROP TABLE IF EXISTS test_apply')\n"
    )
    engine = MigrationEngine(mem_db, migrations_dir)
    await engine.ensure_table()
    mig = MigrationFile(id=mig_file.stem, path=mig_file)
    await engine.apply(mig)
    assert await mem_db.table_exists("test_apply") is True
    row = await mem_db.fetch_one("SELECT id FROM _schema_migrations WHERE id = ?", (mig_file.stem,))
    assert row is not None


async def test_apply_wraps_errors(mem_db, migrations_dir):
    mig_file = migrations_dir / "20260409_200000_bad.py"
    mig_file.write_text(
        "async def up(db):\n"
        "    raise RuntimeError('boom')\n"
        "\n"
        "async def down(db):\n"
        "    pass\n"
    )
    engine = MigrationEngine(mem_db, migrations_dir)
    await engine.ensure_table()
    mig = MigrationFile(id=mig_file.stem, path=mig_file)
    with pytest.raises(RuntimeError, match="20260409_200000_bad"):
        await engine.apply(mig)


async def test_apply_validates_up_function(mem_db, migrations_dir):
    mig_file = migrations_dir / "20260409_300000_no_up.py"
    mig_file.write_text("x = 1\n")
    engine = MigrationEngine(mem_db, migrations_dir)
    await engine.ensure_table()
    mig = MigrationFile(id=mig_file.stem, path=mig_file)
    with pytest.raises(RuntimeError):
        await engine.apply(mig)


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------

async def test_rollback_calls_down_and_removes_record(mem_db, migrations_dir):
    mig_file = migrations_dir / "20260409_100000_create_rb.py"
    mig_file.write_text(
        "async def up(db):\n"
        "    await db.execute('CREATE TABLE rb_table (x INTEGER)')\n"
        "\n"
        "async def down(db):\n"
        "    await db.execute('DROP TABLE IF EXISTS rb_table')\n"
    )
    engine = MigrationEngine(mem_db, migrations_dir)
    await engine.ensure_table()
    mig = MigrationFile(id=mig_file.stem, path=mig_file)
    await engine.apply(mig)
    assert await mem_db.table_exists("rb_table") is True

    result = await engine.rollback()
    assert result is not None
    assert result.id == mig_file.stem
    assert await mem_db.table_exists("rb_table") is False
    row = await mem_db.fetch_one("SELECT id FROM _schema_migrations WHERE id = ?", (mig_file.stem,))
    assert row is None


async def test_rollback_returns_none_when_nothing_applied(mem_db, migrations_dir):
    engine = MigrationEngine(mem_db, migrations_dir)
    result = await engine.rollback()
    assert result is None


async def test_rollback_uses_applied_at_order(mem_db, tmp_path):
    """rollback() removes the migration with the latest applied_at, regardless of filename order."""
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()

    # mig_a comes FIRST alphabetically
    mig_a = migrations_dir / "20260101_000001_a.py"
    mig_a.write_text(
        "async def up(db): await db.execute('CREATE TABLE rb_a (x INTEGER)')\n"
        "async def down(db): await db.execute('DROP TABLE IF EXISTS rb_a')\n"
    )
    # mig_b comes SECOND alphabetically
    mig_b = migrations_dir / "20260101_000002_b.py"
    mig_b.write_text(
        "async def up(db): await db.execute('CREATE TABLE rb_b (x INTEGER)')\n"
        "async def down(db): await db.execute('DROP TABLE IF EXISTS rb_b')\n"
    )

    engine = MigrationEngine(mem_db, migrations_dir)
    await engine.ensure_table()

    # Create both tables manually
    await mem_db.execute("CREATE TABLE rb_a (x INTEGER)")
    await mem_db.execute("CREATE TABLE rb_b (x INTEGER)")

    # Insert applied records with mig_b having EARLIER applied_at than mig_a
    # This means mig_a is the MOST RECENTLY applied, despite being alphabetically first
    await mem_db.execute(
        "INSERT INTO _schema_migrations (id, applied_at) VALUES (?, ?)",
        ("20260101_000002_b", "2026-01-01T00:00:01+00:00"),
    )
    await mem_db.execute(
        "INSERT INTO _schema_migrations (id, applied_at) VALUES (?, ?)",
        ("20260101_000001_a", "2026-01-01T00:00:02+00:00"),  # later timestamp = rolled back first
    )

    # Rollback should pick mig_a (later applied_at), not mig_b (alphabetically last)
    result = await engine.rollback()
    assert result is not None
    assert result.id == "20260101_000001_a"  # most recently applied
    assert not await mem_db.table_exists("rb_a")   # down() ran on mig_a
    assert await mem_db.table_exists("rb_b")  # mig_b untouched

    # mig_a record removed, mig_b still present
    applied = await engine.get_applied()
    assert "20260101_000001_a" not in applied
    assert "20260101_000002_b" in applied


# ---------------------------------------------------------------------------
# run_pending
# ---------------------------------------------------------------------------

async def test_run_pending_multiple(mem_db, migrations_dir):
    for i in range(1, 4):
        f = migrations_dir / f"20260409_1{i}0000_mig{i}.py"
        f.write_text(
            f"async def up(db):\n"
            f"    await db.execute('CREATE TABLE run_pending_{i} (x INTEGER)')\n"
            f"\n"
            f"async def down(db):\n"
            f"    await db.execute('DROP TABLE IF EXISTS run_pending_{i}')\n"
        )
    engine = MigrationEngine(mem_db, migrations_dir)
    applied = await engine.run_pending()
    assert len(applied) == 3
    for i in range(1, 4):
        assert await mem_db.table_exists(f"run_pending_{i}") is True


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

async def test_status_all_pending(mem_db, migrations_dir):
    (migrations_dir / "20260409_100000_a.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    (migrations_dir / "20260409_110000_b.py").write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(mem_db, migrations_dir)
    statuses = await engine.status()
    assert len(statuses) == 2
    assert all(s["status"] == "pending" for s in statuses)


async def test_status_mixed(mem_db, migrations_dir):
    mig1 = migrations_dir / "20260409_100000_done.py"
    mig1.write_text("async def up(db): pass\nasync def down(db): pass\n")
    mig2 = migrations_dir / "20260409_110000_todo.py"
    mig2.write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(mem_db, migrations_dir)
    await engine.ensure_table()
    await mem_db.execute(
        "INSERT INTO _schema_migrations (id, applied_at) VALUES (?, ?)",
        ("20260409_100000_done", "2026-04-09T10:00:00+00:00"),
    )
    statuses = await engine.status()
    by_id = {s["id"]: s for s in statuses}
    assert by_id["20260409_100000_done"]["status"] == "applied"
    assert by_id["20260409_110000_todo"]["status"] == "pending"


async def test_status_orphaned(mem_db, migrations_dir):
    mig_file = migrations_dir / "20260409_100000_orphan.py"
    mig_file.write_text("async def up(db): pass\nasync def down(db): pass\n")
    engine = MigrationEngine(mem_db, migrations_dir)
    await engine.ensure_table()
    await mem_db.execute(
        "INSERT INTO _schema_migrations (id, applied_at) VALUES (?, ?)",
        ("20260409_100000_orphan", "2026-04-09T10:00:00+00:00"),
    )
    # Delete the file to simulate orphan
    mig_file.unlink()
    statuses = await engine.status()
    orphaned = [s for s in statuses if s["status"] == "orphaned"]
    assert len(orphaned) == 1
    assert orphaned[0]["id"] == "20260409_100000_orphan"
