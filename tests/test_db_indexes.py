import pytest
from zeno.collections.schema import Collection, TextField


class TestDbIndexes:
    async def test_get_indexes_empty(self, mem_db):
        await mem_db.execute("CREATE TABLE posts (id TEXT PRIMARY KEY, title TEXT)")
        indexes = await mem_db.get_indexes("posts")
        assert indexes == []

    async def test_get_indexes_after_create(self, mem_db):
        await mem_db.execute("CREATE TABLE posts (id TEXT PRIMARY KEY, title TEXT)")
        await mem_db.execute("CREATE INDEX idx_title ON posts (title)")
        indexes = await mem_db.get_indexes("posts")
        assert "idx_title" in indexes

    async def test_index_exists_true(self, mem_db):
        await mem_db.execute("CREATE TABLE posts (id TEXT PRIMARY KEY, title TEXT)")
        await mem_db.execute("CREATE INDEX idx_title ON posts (title)")
        exists = await mem_db.index_exists("posts", "idx_title")
        assert exists is True

    async def test_index_exists_false(self, mem_db):
        await mem_db.execute("CREATE TABLE posts (id TEXT PRIMARY KEY, title TEXT)")
        exists = await mem_db.index_exists("posts", "idx_nonexistent")
        assert exists is False

    async def test_get_indexes_excludes_pk(self, mem_db):
        await mem_db.execute("CREATE TABLE posts (id TEXT PRIMARY KEY, title TEXT)")
        await mem_db.execute("CREATE INDEX idx_title ON posts (title)")
        indexes = await mem_db.get_indexes("posts")
        pk_indexes = [i for i in indexes if "sqlite_autoindex" in i or "pkey" in i]
        assert pk_indexes == []
