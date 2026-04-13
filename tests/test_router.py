import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from zeno.collections.schema import (
    Collection, TextField, IntField, FloatField, RelationField,
)
from zeno.collections.store import CollectionStore
from zeno.collections.router import build_collection_routes
from zeno.db.connection import Database
from zeno.pipeline import build_middleware_stack


@pytest.fixture
async def app_with_collection(db_path):
    db = Database(db_path)
    await db.connect()
    store = CollectionStore(db)

    posts = Collection("posts", fields=[
        TextField("title", required=True),
        TextField("body"),
        IntField("views", default=0),
    ])
    await store.sync_schema(posts)

    collections = {"posts": (posts, {"read": "public", "write": "public"})}
    routes = build_collection_routes(collections, store)
    app = Starlette(routes=routes)
    app = build_middleware_stack(app)

    yield TestClient(app), db
    await db.disconnect()


class TestCollectionCRUD:
    @pytest.mark.asyncio
    async def test_create(self, app_with_collection):
        client, _ = app_with_collection
        resp = client.post("/api/posts", json={"title": "Hello", "body": "World"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Hello"
        assert data["views"] == 0
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_validation_error(self, app_with_collection):
        client, _ = app_with_collection
        resp = client.post("/api/posts", json={"body": "no title"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_get_single(self, app_with_collection):
        client, _ = app_with_collection
        created = client.post("/api/posts", json={"title": "Test"}).json()
        resp = client.get(f"/api/posts/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Test"

    @pytest.mark.asyncio
    async def test_get_not_found(self, app_with_collection):
        client, _ = app_with_collection
        resp = client.get("/api/posts/nonexistent-uuid")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list(self, app_with_collection):
        client, _ = app_with_collection
        client.post("/api/posts", json={"title": "A"})
        client.post("/api/posts", json={"title": "B"})
        resp = client.get("/api/posts")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_pagination(self, app_with_collection):
        client, _ = app_with_collection
        for i in range(5):
            client.post("/api/posts", json={"title": f"Post {i}"})
        resp = client.get("/api/posts?limit=2&offset=0")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_list_filter(self, app_with_collection):
        client, _ = app_with_collection
        client.post("/api/posts", json={"title": "Draft", "views": 0})
        client.post("/api/posts", json={"title": "Popular", "views": 100})
        resp = client.get("/api/posts?views=100")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Popular"

    @pytest.mark.asyncio
    async def test_update(self, app_with_collection):
        client, _ = app_with_collection
        created = client.post("/api/posts", json={"title": "Old"}).json()
        resp = client.patch(f"/api/posts/{created['id']}", json={"title": "New"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "New"

    @pytest.mark.asyncio
    async def test_update_not_found(self, app_with_collection):
        client, _ = app_with_collection
        resp = client.patch("/api/posts/nonexistent", json={"title": "X"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete(self, app_with_collection):
        client, _ = app_with_collection
        created = client.post("/api/posts", json={"title": "Delete me"}).json()
        resp = client.delete(f"/api/posts/{created['id']}")
        assert resp.status_code == 200
        resp2 = client.get(f"/api/posts/{created['id']}")
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(self, app_with_collection):
        client, _ = app_with_collection
        resp = client.delete("/api/posts/nonexistent")
        assert resp.status_code == 404


class TestExpand:
    @pytest.mark.asyncio
    async def test_expand_relation(self, db_path):
        db = Database(db_path)
        await db.connect()
        store = CollectionStore(db)

        categories = Collection("categories", fields=[
            TextField("name", required=True),
        ])
        products = Collection("products", fields=[
            TextField("name", required=True),
            RelationField("category", collection="categories"),
        ])
        await store.sync_schema(categories)
        await store.sync_schema(products)

        collections = {
            "categories": (categories, {"read": "public", "write": "public"}),
            "products": (products, {"read": "public", "write": "public"}),
        }
        routes = build_collection_routes(collections, store)
        app = Starlette(routes=routes)
        app = build_middleware_stack(app)
        client = TestClient(app)

        cat = client.post("/api/categories", json={"name": "Electronics"}).json()
        prod = client.post("/api/products", json={
            "name": "Phone", "category": cat["id"]
        }).json()

        resp = client.get(f"/api/products/{prod['id']}?expand=category")
        data = resp.json()
        assert "expand" in data
        assert data["expand"]["category"]["name"] == "Electronics"

        await db.disconnect()

    @pytest.mark.asyncio
    async def test_expand_multiple_relations(self, db_path):
        """?expand=a,b expands two relation fields in a single request."""
        db = Database(db_path)
        await db.connect()
        store = CollectionStore(db)

        authors = Collection("authors", fields=[TextField("name", required=True)])
        categories = Collection("categories2", fields=[TextField("label", required=True)])
        articles = Collection("articles", fields=[
            TextField("title", required=True),
            RelationField("author", collection="authors"),
            RelationField("category", collection="categories2"),
        ])
        await store.sync_schema(authors)
        await store.sync_schema(categories)
        await store.sync_schema(articles)

        collections = {
            "authors":      (authors,     {"read": "public", "write": "public"}),
            "categories2":  (categories,  {"read": "public", "write": "public"}),
            "articles":     (articles,    {"read": "public", "write": "public"}),
        }
        routes = build_collection_routes(collections, store)
        client = TestClient(build_middleware_stack(Starlette(routes=routes)))

        author = client.post("/api/authors", json={"name": "Alice"}).json()
        cat    = client.post("/api/categories2", json={"label": "Tech"}).json()
        art    = client.post("/api/articles", json={
            "title": "Hello", "author": author["id"], "category": cat["id"],
        }).json()

        resp = client.get(f"/api/articles/{art['id']}?expand=author,category")
        data = resp.json()
        assert data["expand"]["author"]["name"] == "Alice"
        assert data["expand"]["category"]["label"] == "Tech"

        await db.disconnect()

    @pytest.mark.asyncio
    async def test_expand_on_list_endpoint(self, db_path):
        """?expand= works on GET /api/{collection} list responses."""
        db = Database(db_path)
        await db.connect()
        store = CollectionStore(db)

        brands = Collection("brands", fields=[TextField("name", required=True)])
        items = Collection("items", fields=[
            TextField("sku", required=True),
            RelationField("brand", collection="brands"),
        ])
        await store.sync_schema(brands)
        await store.sync_schema(items)

        collections = {
            "brands": (brands, {"read": "public", "write": "public"}),
            "items":  (items,  {"read": "public", "write": "public"}),
        }
        routes = build_collection_routes(collections, store)
        client = TestClient(build_middleware_stack(Starlette(routes=routes)))

        brand = client.post("/api/brands", json={"name": "Acme"}).json()
        client.post("/api/items", json={"sku": "A1", "brand": brand["id"]})
        client.post("/api/items", json={"sku": "A2", "brand": brand["id"]})

        resp = client.get("/api/items?expand=brand")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert "expand" in item
            assert item["expand"]["brand"]["name"] == "Acme"

        await db.disconnect()

    @pytest.mark.asyncio
    async def test_expand_invalid_field_ignored(self, db_path):
        """Expanding a field that is not a RelationField should not crash."""
        db = Database(db_path)
        await db.connect()
        store = CollectionStore(db)

        notes = Collection("notes", fields=[TextField("body")])
        await store.sync_schema(notes)

        collections = {"notes": (notes, {"read": "public", "write": "public"})}
        routes = build_collection_routes(collections, store)
        client = TestClient(build_middleware_stack(Starlette(routes=routes)))

        note = client.post("/api/notes", json={"body": "hello"}).json()
        resp = client.get(f"/api/notes/{note['id']}?expand=nonexistent")
        assert resp.status_code == 200  # graceful — no crash

        await db.disconnect()


class TestUniqueConstraints:
    @pytest.mark.asyncio
    async def test_create_duplicate_unique_field_returns_400(self, db_path):
        db = Database(db_path)
        await db.connect()
        store = CollectionStore(db)

        users = Collection("uniq_users", fields=[
            TextField("email", required=True, unique=True),
        ])
        await store.sync_schema(users)

        collections = {"uniq_users": (users, {"read": "public", "write": "public"})}
        routes = build_collection_routes(collections, store)
        client = TestClient(build_middleware_stack(Starlette(routes=routes)))

        resp1 = client.post("/api/uniq_users", json={"email": "dup@example.com"})
        assert resp1.status_code == 201

        resp2 = client.post("/api/uniq_users", json={"email": "dup@example.com"})
        assert resp2.status_code == 400

        await db.disconnect()

    @pytest.mark.asyncio
    async def test_update_to_duplicate_unique_field_returns_400(self, db_path):
        db = Database(db_path)
        await db.connect()
        store = CollectionStore(db)

        people = Collection("people", fields=[
            TextField("handle", required=True, unique=True),
        ])
        await store.sync_schema(people)

        collections = {"people": (people, {"read": "public", "write": "public"})}
        routes = build_collection_routes(collections, store)
        client = TestClient(build_middleware_stack(Starlette(routes=routes)))

        a = client.post("/api/people", json={"handle": "alice"}).json()
        client.post("/api/people", json={"handle": "bob"})

        # Try to rename alice → bob (conflict)
        resp = client.patch(f"/api/people/{a['id']}", json={"handle": "bob"})
        assert resp.status_code == 400

        await db.disconnect()


class TestFieldConstraintsAtHTTPLayer:
    @pytest.mark.asyncio
    async def test_int_field_min_value_rejected(self, db_path):
        db = Database(db_path)
        await db.connect()
        store = CollectionStore(db)

        things = Collection("things", fields=[
            IntField("qty", required=True, min_value=1),
        ])
        await store.sync_schema(things)

        collections = {"things": (things, {"read": "public", "write": "public"})}
        routes = build_collection_routes(collections, store)
        client = TestClient(build_middleware_stack(Starlette(routes=routes)))

        resp = client.post("/api/things", json={"qty": 0})
        assert resp.status_code == 400

        resp_ok = client.post("/api/things", json={"qty": 5})
        assert resp_ok.status_code == 201

        await db.disconnect()

    @pytest.mark.asyncio
    async def test_float_field_max_value_rejected(self, db_path):
        db = Database(db_path)
        await db.connect()
        store = CollectionStore(db)

        ratings = Collection("ratings", fields=[
            FloatField("score", required=True, min_value=0.0, max_value=5.0),
        ])
        await store.sync_schema(ratings)

        collections = {"ratings": (ratings, {"read": "public", "write": "public"})}
        routes = build_collection_routes(collections, store)
        client = TestClient(build_middleware_stack(Starlette(routes=routes)))

        resp = client.post("/api/ratings", json={"score": 9.9})
        assert resp.status_code == 400

        resp = client.post("/api/ratings", json={"score": -1.0})
        assert resp.status_code == 400

        resp_ok = client.post("/api/ratings", json={"score": 4.5})
        assert resp_ok.status_code == 201

        await db.disconnect()

    @pytest.mark.asyncio
    async def test_multiple_required_fields_missing_returns_400(self, db_path):
        db = Database(db_path)
        await db.connect()
        store = CollectionStore(db)

        orders = Collection("orders", fields=[
            TextField("product", required=True),
            TextField("customer", required=True),
            IntField("qty", required=True),
        ])
        await store.sync_schema(orders)

        collections = {"orders": (orders, {"read": "public", "write": "public"})}
        routes = build_collection_routes(collections, store)
        client = TestClient(build_middleware_stack(Starlette(routes=routes)))

        # Entirely empty body
        assert client.post("/api/orders", json={}).status_code == 400
        # Only one of three required fields
        assert client.post("/api/orders", json={"product": "widget"}).status_code == 400
        # All required
        resp = client.post("/api/orders", json={
            "product": "widget", "customer": "alice", "qty": 2,
        })
        assert resp.status_code == 201

        await db.disconnect()
