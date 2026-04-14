import pytest


@pytest.fixture
def db_path(tmp_path):
    """Return a path to a temporary SQLite database file."""
    return str(tmp_path / "test.db")


@pytest.fixture
async def mem_db():
    """In-memory SQLite database for unit tests."""
    from zeno.db.connection import Database

    db = Database(":memory:")
    await db.connect()
    yield db
    await db.disconnect()
