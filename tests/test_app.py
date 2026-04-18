import pytest
from starlette.testclient import TestClient

from zork.app import Zork
from zork.auth import Auth
from zork.collections.schema import Collection, IntField, TextField


@pytest.fixture
def app(db_path):
    zork = Zork(database=db_path)

    posts = Collection(
        "posts",
        fields=[
            TextField("title", required=True),
            TextField("body"),
            IntField("views", default=0),
        ],
    )
    zork.register(posts, auth=["read:public", "write:public"])
    return zork


@pytest.fixture
def app_with_auth(db_path):
    zork = Zork(database=db_path)

    posts = Collection(
        "posts",
        fields=[
            TextField("title", required=True),
        ],
    )
    auth = Auth(token_expiry=3600, allow_registration=True)

    zork.register(posts, auth=["read:public", "write:authenticated"])
    zork.use_auth(auth)
    return zork


class TestZorkApp:
    def test_build_creates_working_app(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.post("/api/posts", json={"title": "Hello"})
        assert resp.status_code == 201

        resp = client.get("/api/posts")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_collections_registered(self, app):
        assert "posts" in app._collections

    def test_health_check(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestZorkWithAuth:
    def test_auth_routes_available(self, app_with_auth):
        starlette_app = app_with_auth.build()
        client = TestClient(starlette_app)

        resp = client.post(
            "/api/auth/register",
            json={
                "email": "test@test.com",
                "password": "password123",
            },
        )
        assert resp.status_code == 201
        token = resp.json()["token"]

        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_authenticated_write_requires_token(self, app_with_auth):
        starlette_app = app_with_auth.build()
        client = TestClient(starlette_app)

        resp = client.post("/api/posts", json={"title": "Unauthorized"})
        assert resp.status_code == 401

    def test_authenticated_write_with_token(self, app_with_auth):
        starlette_app = app_with_auth.build()
        client = TestClient(starlette_app)

        reg = client.post(
            "/api/auth/register",
            json={
                "email": "writer@test.com",
                "password": "password123",
            },
        ).json()
        token = reg["token"]

        resp = client.post(
            "/api/posts",
            json={"title": "Authorized"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

    def test_public_read_without_token(self, app_with_auth):
        starlette_app = app_with_auth.build()
        client = TestClient(starlette_app)

        resp = client.get("/api/posts")
        assert resp.status_code == 200


class TestAPIVersioning:
    def test_no_version_default_prefix(self, db_path):
        """Default: no versioning, routes at /api"""
        zork = Zork(database=db_path)
        posts = Collection("posts", fields=[TextField("title", required=True)])
        zork.register(posts)

        starlette_app = zork.build()
        client = TestClient(starlette_app)

        assert zork.version_prefix is None
        resp = client.get("/api/posts")
        assert resp.status_code == 200

    def test_version_v1_prefix(self, db_path):
        """When version is set, routes use version prefix"""
        zork = Zork(database=db_path, version="v1")
        posts = Collection("posts", fields=[TextField("title", required=True)])
        zork.register(posts)

        assert zork.version_prefix == "/api/v1"

        starlette_app = zork.build()
        client = TestClient(starlette_app)

        # Old routes should not work
        resp = client.get("/api/posts")
        assert resp.status_code == 404
        # New versioned routes should work
        resp = client.get("/api/v1/posts")
        assert resp.status_code == 200

    def test_version_without_v_prefix(self, db_path):
        """Version without 'v' prefix should add it"""
        zork = Zork(database=db_path, version="2")
        posts = Collection("posts", fields=[TextField("title")])
        zork.register(posts)

        assert zork.version_prefix == "/api/v2"

        starlette_app = zork.build()
        client = TestClient(starlette_app)

        resp = client.get("/api/v2/posts")
        assert resp.status_code == 200

    def test_custom_prefix(self, db_path):
        """Custom prefix should be used"""
        zork = Zork(database=db_path, version="v1", version_prefix="/custom")
        posts = Collection("posts", fields=[TextField("title")])
        zork.register(posts)

        assert zork.version_prefix == "/custom/v1"

        starlette_app = zork.build()
        client = TestClient(starlette_app)

        resp = client.get("/custom/v1/posts")
        assert resp.status_code == 200

    def test_version_with_auth(self, db_path):
        """Versioned auth routes work correctly"""
        zork = Zork(database=db_path, version="v1")
        auth = Auth(token_expiry=3600, allow_registration=True)
        zork.use_auth(auth)

        starlette_app = zork.build()
        client = TestClient(starlette_app)

        # Auth routes should be versioned
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "password": "securepass123",
            },
        )
        assert resp.status_code == 201

    def test_openapi_version_in_response(self, db_path):
        """OpenAPI should include version in route"""
        zork = Zork(database=db_path, version="v1", title="My API")
        posts = Collection("posts", fields=[TextField("title")])
        zork.register(posts)

        starlette_app = zork.build()
        client = TestClient(starlette_app)

        resp = client.get("/api/v1/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["info"]["title"] == "My API"
