import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from zeno.auth import Auth
from zeno.auth.models import create_auth_tables
from zeno.auth.routes import build_auth_routes
from zeno.db.connection import Database
from zeno.pipeline import build_middleware_stack

SECRET = "test-secret-for-auth-tests"


@pytest.fixture
async def auth_app(db_path):
    db = Database(db_path)
    await db.connect()

    auth = Auth(token_expiry=3600, allow_registration=True)
    await create_auth_tables(db)

    routes = build_auth_routes(auth, db, SECRET)
    app = Starlette(routes=routes)
    app = build_middleware_stack(app)

    yield TestClient(app), db, auth
    await db.disconnect()


def register_user(client, email="test@example.com", password="password123"):
    return client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
        },
    )


class TestRegister:
    @pytest.mark.asyncio
    async def test_register_success(self, auth_app):
        client, db, auth = auth_app
        resp = register_user(client)
        assert resp.status_code == 201
        data = resp.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "test@example.com"
        assert data["user"]["role"] == "user"
        assert "password" not in data["user"]

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, auth_app):
        client, db, auth = auth_app
        register_user(client)
        resp = register_user(client)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_register_disabled(self, db_path):
        db = Database(db_path)
        await db.connect()
        auth = Auth(allow_registration=False)
        await create_auth_tables(db)
        routes = build_auth_routes(auth, db, SECRET)
        app = build_middleware_stack(Starlette(routes=routes))
        client = TestClient(app)

        resp = register_user(client)
        assert resp.status_code == 403
        await db.disconnect()


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, auth_app):
        client, db, auth = auth_app
        register_user(client)
        resp = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "password123",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, auth_app):
        client, db, auth = auth_app
        register_user(client)
        resp = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "wrongpassword",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, auth_app):
        client, db, auth = auth_app
        resp = client.post(
            "/api/auth/login",
            json={
                "email": "nobody@example.com",
                "password": "password123",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, auth_app):
        client, db, auth = auth_app
        register_user(client)
        await db.execute(
            "UPDATE _users SET is_active = 0 WHERE email = ?", ("test@example.com",)
        )
        resp = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "password123",
            },
        )
        assert resp.status_code == 403


class TestMe:
    @pytest.mark.asyncio
    async def test_me_with_valid_token(self, auth_app):
        client, db, auth = auth_app
        reg = register_user(client).json()
        token = reg["token"]
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "test@example.com"
        assert "password" not in resp.json()

    @pytest.mark.asyncio
    async def test_me_without_token(self, auth_app):
        client, db, auth = auth_app
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401


class TestLogout:
    @pytest.mark.asyncio
    async def test_logout(self, auth_app):
        client, db, auth = auth_app
        reg = register_user(client).json()
        token = reg["token"]
        resp = client.post(
            "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        resp2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 401


class TestRefresh:
    @pytest.mark.asyncio
    async def test_refresh_token(self, auth_app):
        client, db, auth = auth_app
        reg = register_user(client).json()
        old_token = reg["token"]
        resp = client.post(
            "/api/auth/refresh", headers={"Authorization": f"Bearer {old_token}"}
        )
        assert resp.status_code == 200
        new_token = resp.json()["token"]
        assert new_token != old_token
        resp2 = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
        )
        assert resp2.status_code == 401
        resp3 = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {new_token}"}
        )
        assert resp3.status_code == 200
