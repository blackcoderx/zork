"""End-to-end integration test matching the example from the Zeno spec."""
import pytest
from starlette.testclient import TestClient

from zeno.app import Zeno
from zeno.auth import Auth
from zeno.collections.schema import (
    Collection, TextField, IntField, FloatField, RelationField, BoolField,
)


@pytest.fixture
def e2e_app(db_path):
    app = Zeno(database=db_path)

    categories = Collection("categories", fields=[
        TextField("name", required=True),
    ])

    products = Collection("products", fields=[
        TextField("name", required=True),
        TextField("description"),
        FloatField("price", required=True),
        IntField("stock", default=0),
        BoolField("is_published", default=False),
        RelationField("category", collection="categories"),
    ])

    auth = Auth(token_expiry=3600, allow_registration=True)

    app.register(categories, auth=["read:public", "write:authenticated"])
    app.register(products, auth=["read:public", "write:authenticated"])
    app.use_auth(auth)

    with TestClient(app.build()) as client:
        yield client


class TestEndToEnd:
    def test_full_flow(self, e2e_app):
        client = e2e_app

        # 1. Register a user
        reg = client.post("/api/auth/register", json={
            "email": "shop@example.com",
            "password": "secure123",
        })
        assert reg.status_code == 201
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Public read before any data exists
        resp = client.get("/api/products")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

        # 3. Create a category (requires auth)
        cat = client.post("/api/categories", json={"name": "Electronics"}, headers=headers)
        assert cat.status_code == 201
        cat_id = cat.json()["id"]

        # 4. Create a product
        prod = client.post("/api/products", json={
            "name": "Phone",
            "description": "A smartphone",
            "price": 999.99,
            "stock": 50,
            "is_published": True,
            "category": cat_id,
        }, headers=headers)
        assert prod.status_code == 201
        prod_id = prod.json()["id"]
        assert prod.json()["price"] == 999.99
        assert prod.json()["stock"] == 50
        assert prod.json()["is_published"] is True

        # 5. Read with expand
        resp = client.get(f"/api/products/{prod_id}?expand=category")
        assert resp.status_code == 200
        data = resp.json()
        assert data["expand"]["category"]["name"] == "Electronics"

        # 6. Update product
        resp = client.patch(f"/api/products/{prod_id}", json={"stock": 49}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["stock"] == 49

        # 7. List with filters
        client.post("/api/products", json={
            "name": "Laptop", "price": 1499.99, "stock": 10
        }, headers=headers)
        resp = client.get("/api/products?stock=49")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["name"] == "Phone"

        # 8. Pagination
        resp = client.get("/api/products?limit=1&offset=0")
        assert resp.json()["total"] == 2
        assert len(resp.json()["items"]) == 1

        # 9. Delete
        resp = client.delete(f"/api/products/{prod_id}", headers=headers)
        assert resp.status_code == 200
        resp = client.get(f"/api/products/{prod_id}")
        assert resp.status_code == 404

        # 10. Auth flow: login, me, logout
        login = client.post("/api/auth/login", json={
            "email": "shop@example.com",
            "password": "secure123",
        })
        assert login.status_code == 200
        new_token = login.json()["token"]

        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
        assert me.status_code == 200
        assert me.json()["email"] == "shop@example.com"

        logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {new_token}"})
        assert logout.status_code == 200

        # Token should be revoked
        me2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
        assert me2.status_code == 401

        # 11. Health check
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_unauthenticated_write_rejected(self, e2e_app):
        client = e2e_app
        resp = client.post("/api/categories", json={"name": "Test"})
        assert resp.status_code == 401

    def test_middleware_headers(self, e2e_app):
        client = e2e_app
        resp = client.get("/api/health")
        assert "x-request-id" in resp.headers
