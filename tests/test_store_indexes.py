import pytest
from zeno.collections.schema import Collection, TextField
from zeno.collections.store import CollectionStore


class TestStoreIndexes:
    async def test_sync_schema_creates_indexes(self, mem_db):
        collection = Collection("posts", fields=[TextField("category", indexed=True)])
        store = CollectionStore(mem_db)
        await store.sync_schema(collection)

        indexes = await mem_db.get_indexes("posts")
        assert "idx_posts_category" in indexes

    async def test_sync_schema_idempotent_indexes(self, mem_db):
        collection = Collection("posts", fields=[TextField("category", indexed=True)])
        store = CollectionStore(mem_db)
        await store.sync_schema(collection)
        await store.sync_schema(collection)

        indexes = await mem_db.get_indexes("posts")
        assert "idx_posts_category" in indexes

    async def test_sync_schema_does_not_drop_indexes(self, mem_db):
        await mem_db.execute("CREATE TABLE posts (id TEXT PRIMARY KEY, title TEXT)")
        await mem_db.execute("CREATE INDEX idx_manual ON posts (title)")

        collection = Collection("posts", fields=[TextField("category", indexed=True)])
        store = CollectionStore(mem_db)
        await store.sync_schema(collection)

        indexes = await mem_db.get_indexes("posts")
        assert "idx_manual" in indexes
        assert "idx_posts_category" in indexes

    async def test_sync_schema_composite_index(self, mem_db):
        collection = Collection(
            "posts",
            fields=[
                TextField("category"),
                TextField("published_at"),
            ],
            indexes=[("category", "published_at")],
        )
        store = CollectionStore(mem_db)
        await store.sync_schema(collection)

        indexes = await mem_db.get_indexes("posts")
        assert "idx_posts_category_published_at" in indexes
