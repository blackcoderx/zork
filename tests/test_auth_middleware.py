import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from zeno.auth.models import create_auth_tables, block_token
from zeno.auth.tokens import create_token, decode_token
from zeno.db.connection import Database
from zeno.pipeline import build_middleware_stack, AuthMiddleware


SECRET = "test-middleware-secret"


async def user_endpoint(request: Request):
    user = getattr(request.state, "user", None)
    if user is None:
        return JSONResponse({"user": None})
    return JSONResponse({"user": user})


@pytest.fixture
async def middleware_app(db_path):
    db = Database(db_path)
    await db.connect()
    await create_auth_tables(db)

    await db.execute(
        "INSERT INTO _users (id, email, password, is_active, role, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("user-1", "test@test.com", "hashed", 1, "user", "2026-01-01", "2026-01-01"),
    )

    app = Starlette(routes=[Route("/test", user_endpoint)])
    app = build_middleware_stack(app, db=db, secret=SECRET)

    yield TestClient(app), db
    await db.disconnect()


class TestAuthMiddleware:
    @pytest.mark.asyncio
    async def test_no_token_sets_user_none(self, middleware_app):
        client, _ = middleware_app
        resp = client.get("/test")
        assert resp.json()["user"] is None

    @pytest.mark.asyncio
    async def test_valid_token_sets_user(self, middleware_app):
        client, _ = middleware_app
        token = create_token("user-1", "user", 3600, SECRET)
        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()
        assert data["user"] is not None
        assert data["user"]["id"] == "user-1"
        assert data["user"]["email"] == "test@test.com"
        assert "password" not in data["user"]

    @pytest.mark.asyncio
    async def test_invalid_token_sets_user_none(self, middleware_app):
        client, _ = middleware_app
        resp = client.get("/test", headers={"Authorization": "Bearer garbage"})
        assert resp.json()["user"] is None

    @pytest.mark.asyncio
    async def test_blocked_token_sets_user_none(self, middleware_app):
        client, db = middleware_app
        token = create_token("user-1", "user", 3600, SECRET)
        payload = decode_token(token, SECRET)
        await block_token(db, payload["jti"], "2099-01-01T00:00:00")
        resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["user"] is None
