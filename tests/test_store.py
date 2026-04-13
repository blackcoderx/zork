import pytest
from zeno.db.connection import Database
from zeno.collections.schema import (
    Collection, TextField, IntField, BoolField, FloatField, JSONField,
)
from zeno.collections.store import CollectionStore


@pytest.fixture
async def db(db_path):
    database = Database(db_path)
    await database.connect()
    yield database
    await database.disconnect()


@pytest.fixture
async def store(db):
    return CollectionStore(db)


@pytest.fixture
def posts_collection():
    return Collection("posts", fields=[
        TextField("title", required=True),
        TextField("body"),
        IntField("views", default=0),
    ])


class TestSchemaSync:
    @pytest.mark.asyncio
    async def test_creates_table_on_sync(self, store, db, posts_collection):
        await store.sync_schema(posts_collection)
        row = await db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("posts",),
        )
        assert row is not None

    @pytest.mark.asyncio
    async def test_table_has_auto_columns(self, store, db, posts_collection):
        await store.sync_schema(posts_collection)
        columns = await db.fetch_all("PRAGMA table_info(posts)")
        col_names = [c["name"] for c in columns]
        assert "id" in col_names
        assert "created_at" in col_names
        assert "updated_at" in col_names

    @pytest.mark.asyncio
    async def test_adds_new_columns_on_resync(self, store, db):
        v1 = Collection("items", fields=[TextField("name")])
        await store.sync_schema(v1)

        v2 = Collection("items", fields=[
            TextField("name"),
            IntField("quantity"),
        ])
        await store.sync_schema(v2)

        columns = await db.fetch_all("PRAGMA table_info(items)")
        col_names = [c["name"] for c in columns]
        assert "quantity" in col_names

    @pytest.mark.asyncio
    async def test_warns_on_removed_columns(self, store, db, caplog):
        import logging
        v1 = Collection("items", fields=[
            TextField("name"),
            IntField("old_field"),
        ])
        await store.sync_schema(v1)

        v2 = Collection("items", fields=[TextField("name")])
        with caplog.at_level(logging.WARNING):
            await store.sync_schema(v2)
        assert "old_field" in caplog.text


class TestCRUD:
    @pytest.mark.asyncio
    async def test_create_record(self, store, posts_collection):
        await store.sync_schema(posts_collection)
        record = await store.create(posts_collection, {"title": "Hello", "body": "World"})
        assert record["title"] == "Hello"
        assert record["body"] == "World"
        assert record["views"] == 0
        assert "id" in record
        assert "created_at" in record
        assert "updated_at" in record

    @pytest.mark.asyncio
    async def test_create_validates_required(self, store, posts_collection):
        await store.sync_schema(posts_collection)
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            await store.create(posts_collection, {"body": "no title"})

    @pytest.mark.asyncio
    async def test_get_record(self, store, posts_collection):
        await store.sync_schema(posts_collection)
        created = await store.create(posts_collection, {"title": "Test"})
        fetched = await store.get(posts_collection, created["id"])
        assert fetched is not None
        assert fetched["title"] == "Test"

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing(self, store, posts_collection):
        await store.sync_schema(posts_collection)
        result = await store.get(posts_collection, "nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_records(self, store, posts_collection):
        await store.sync_schema(posts_collection)
        await store.create(posts_collection, {"title": "A"})
        await store.create(posts_collection, {"title": "B"})
        await store.create(posts_collection, {"title": "C"})
        items, total = await store.list(posts_collection)
        assert total == 3
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_list_with_pagination(self, store, posts_collection):
        await store.sync_schema(posts_collection)
        for i in range(5):
            await store.create(posts_collection, {"title": f"Post {i}"})
        items, total = await store.list(posts_collection, limit=2, offset=0)
        assert total == 5
        assert len(items) == 2
        items2, _ = await store.list(posts_collection, limit=2, offset=2)
        assert len(items2) == 2

    @pytest.mark.asyncio
    async def test_list_with_filters(self, store, posts_collection):
        await store.sync_schema(posts_collection)
        await store.create(posts_collection, {"title": "Draft", "views": 0})
        await store.create(posts_collection, {"title": "Popular", "views": 100})
        items, total = await store.list(posts_collection, filters={"views": 100})
        assert total == 1
        assert items[0]["title"] == "Popular"

    @pytest.mark.asyncio
    async def test_update_record(self, store, posts_collection):
        await store.sync_schema(posts_collection)
        created = await store.create(posts_collection, {"title": "Old"})
        updated = await store.update(posts_collection, created["id"], {"title": "New"})
        assert updated is not None
        assert updated["title"] == "New"
        assert updated["updated_at"] != created["updated_at"]

    @pytest.mark.asyncio
    async def test_update_returns_none_for_missing(self, store, posts_collection):
        await store.sync_schema(posts_collection)
        result = await store.update(posts_collection, "nonexistent", {"title": "X"})
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_record(self, store, posts_collection):
        await store.sync_schema(posts_collection)
        created = await store.create(posts_collection, {"title": "Delete me"})
        assert await store.delete(posts_collection, created["id"]) is True
        assert await store.get(posts_collection, created["id"]) is None

    @pytest.mark.asyncio
    async def test_delete_returns_false_for_missing(self, store, posts_collection):
        await store.sync_schema(posts_collection)
        assert await store.delete(posts_collection, "nonexistent") is False

    @pytest.mark.asyncio
    async def test_bool_field_serialization(self, store, db):
        c = Collection("flags", fields=[BoolField("active", default=True)])
        await store.sync_schema(c)
        record = await store.create(c, {"active": True})
        assert record["active"] is True
        fetched = await store.get(c, record["id"])
        assert fetched["active"] is True

    @pytest.mark.asyncio
    async def test_json_field_serialization(self, store, db):
        c = Collection("configs", fields=[JSONField("data")])
        await store.sync_schema(c)
        record = await store.create(c, {"data": {"key": "value", "nums": [1, 2]}})
        assert record["data"] == {"key": "value", "nums": [1, 2]}
        fetched = await store.get(c, record["id"])
        assert fetched["data"] == {"key": "value", "nums": [1, 2]}
