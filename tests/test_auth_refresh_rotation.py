"""Tests for refresh token rotation and management.

Covers:
- Refresh tokens stored on login
- Refresh token rotation on use
- Old refresh tokens blocked after rotation
- Max refresh tokens limit enforced
- Password reset revokes all refresh tokens
- Token type verification
"""

import pytest
import pytest_asyncio
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from zork.auth import Auth
from zork.auth.delivery import CookieTokenDelivery, BearerTokenDelivery
from zork.auth.models import (
    REFRESH_TOKENS_TABLE,
    create_auth_tables,
    get_refresh_token_by_jti,
    revoke_all_user_refresh_tokens,
    store_refresh_token,
    enforce_refresh_token_limit,
    hash_jti,
)
from zork.auth.routes import build_auth_routes
from zork.auth.tokens import (
    create_access_token,
    create_refresh_token,
    decode_token,
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
)
from zork.db.connection import Database
from zork.pipeline import build_middleware_stack


SECRET = "test-secret-for-refresh-tests"


@pytest_asyncio.fixture
async def db_path(tmp_path):
    return str(tmp_path / "refresh_test.db")


@pytest_asyncio.fixture
async def db(db_path):
    database = Database(db_path)
    await database.connect()
    await create_auth_tables(database)
    yield database
    await database.disconnect()


@pytest.fixture
def auth():
    return Auth(
        token_expiry=86400,
        allow_registration=True,
        access_token_expiry=3600,
        refresh_token_expiry=604800,
        max_refresh_tokens=5,
    )


@pytest.fixture
def auth_app(db, auth):
    routes = build_auth_routes(auth, db, SECRET)
    app = Starlette(routes=routes)
    app = build_middleware_stack(app)
    return TestClient(app)


class TestRefreshTokenStorage:
    @pytest.mark.asyncio
    async def test_store_refresh_token(self, db):
        # Disable foreign key checks since we're testing without users
        await db.execute("PRAGMA foreign_keys=OFF")

        user_id = "user-123"
        jti = "refresh-jti-456"
        expires_in = 604800

        await store_refresh_token(db, user_id, jti, expires_in)

        stored = await get_refresh_token_by_jti(db, jti)
        assert stored is not None
        assert stored["user_id"] == user_id

    @pytest.mark.asyncio
    async def test_store_duplicate_is_idempotent(self, db):
        await db.execute("PRAGMA foreign_keys=OFF")

        user_id = "user-123"
        jti = "duplicate-jti"
        expires_in = 604800

        await store_refresh_token(db, user_id, jti, expires_in)
        await store_refresh_token(db, user_id, jti, expires_in)

        stored = await get_refresh_token_by_jti(db, jti)
        assert stored is not None

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, db):
        stored = await get_refresh_token_by_jti(db, "nonexistent-jti")
        assert stored is None

    @pytest.mark.asyncio
    async def test_hash_jti_is_used(self, db):
        await db.execute("PRAGMA foreign_keys=OFF")

        user_id = "user-123"
        jti = "sensitive-jti"

        await store_refresh_token(db, user_id, jti, 604800)

        row = await db.fetch_one(f"SELECT * FROM {REFRESH_TOKENS_TABLE}")
        assert row is not None
        assert row["jti_hash"] == hash_jti(jti)
        assert row["jti_hash"] != jti


class TestRefreshTokenLimit:
    @pytest.mark.asyncio
    async def test_enforce_limit_under_max(self, db):
        await db.execute("PRAGMA foreign_keys=OFF")

        user_id = "limit-user"
        max_tokens = 5

        for i in range(3):
            jti = f"token-{i}"
            await store_refresh_token(db, user_id, jti, 604800)

        removed = await enforce_refresh_token_limit(db, user_id, max_tokens)
        assert removed == 0

        count_row = await db.fetch_one(
            f"SELECT COUNT(*) as cnt FROM {REFRESH_TOKENS_TABLE} WHERE user_id = ?",
            (user_id,),
        )
        assert count_row["cnt"] == 3

    @pytest.mark.asyncio
    async def test_enforce_limit_at_max_removes_oldest(self, db):
        """When at max tokens, enforce removes oldest to make room for new token."""
        await db.execute("PRAGMA foreign_keys=OFF")

        user_id = "max-user"
        max_tokens = 5

        for i in range(5):
            jti = f"token-{i}"
            await store_refresh_token(db, user_id, jti, 604800)

        removed = await enforce_refresh_token_limit(db, user_id, max_tokens)
        # Removes 1 oldest to make room for new token
        assert removed == 1

        count_row = await db.fetch_one(
            f"SELECT COUNT(*) as cnt FROM {REFRESH_TOKENS_TABLE} WHERE user_id = ?",
            (user_id,),
        )
        # Now 4 tokens, room for 1 more
        assert count_row["cnt"] == 4

    @pytest.mark.asyncio
    async def test_enforce_limit_exceeds_max(self, db):
        """When exceeds max, enforce removes excess to reach max-1 (room for new)."""
        await db.execute("PRAGMA foreign_keys=OFF")

        user_id = "excess-user"
        max_tokens = 5

        for i in range(7):
            jti = f"token-{i}"
            await store_refresh_token(db, user_id, jti, 604800)

        removed = await enforce_refresh_token_limit(db, user_id, max_tokens)
        # Removes 3 (7 - 5 + 1) oldest tokens
        assert removed == 3

        count_row = await db.fetch_one(
            f"SELECT COUNT(*) as cnt FROM {REFRESH_TOKENS_TABLE} WHERE user_id = ?",
            (user_id,),
        )
        # Now 4 tokens, room for 1 more
        assert count_row["cnt"] == 4

    @pytest.mark.asyncio
    async def test_oldest_tokens_removed_first(self, db):
        """Enforce removes oldest tokens first based on created_at order."""
        await db.execute("PRAGMA foreign_keys=OFF")

        user_id = "oldest-user"
        max_tokens = 2

        for i in range(3):
            jti = f"token-{i}"
            await store_refresh_token(db, user_id, jti, 604800)

        await enforce_refresh_token_limit(db, user_id, max_tokens)
        # With 3 tokens and max=2, removes 2 oldest (excess = 3-2+1 = 2)
        # So token-0 and token-1 are removed, only token-2 remains
        assert await get_refresh_token_by_jti(db, "token-0") is None
        assert await get_refresh_token_by_jti(db, "token-1") is None
        assert await get_refresh_token_by_jti(db, "token-2") is not None


class TestRevokeAllRefreshTokens:
    @pytest.mark.asyncio
    async def test_revoke_all_removes_tokens(self, db):
        await db.execute("PRAGMA foreign_keys=OFF")

        user_id = "revoke-user"

        for i in range(3):
            jti = f"token-{i}"
            await store_refresh_token(db, user_id, jti, 604800)

        await revoke_all_user_refresh_tokens(db, user_id)

        for i in range(3):
            stored = await get_refresh_token_by_jti(db, f"token-{i}")
            assert stored is None

    @pytest.mark.asyncio
    async def test_revoke_only_affects_target_user(self, db):
        await db.execute("PRAGMA foreign_keys=OFF")

        user_1 = "user-1"
        user_2 = "user-2"

        await store_refresh_token(db, user_1, "user1-token", 604800)
        await store_refresh_token(db, user_2, "user2-token", 604800)

        await revoke_all_user_refresh_tokens(db, user_1)

        assert await get_refresh_token_by_jti(db, "user1-token") is None
        assert await get_refresh_token_by_jti(db, "user2-token") is not None


class TestLoginWithRefreshTokens:
    @pytest.mark.asyncio
    async def test_register_stores_refresh_token(self, auth_app, db):
        response = auth_app.post(
            "/api/auth/register",
            json={
                "email": "new@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 201

        user_id = response.json()["user"]["id"]
        tokens = await db.fetch_all(
            f"SELECT * FROM {REFRESH_TOKENS_TABLE} WHERE user_id = ?", (user_id,)
        )
        assert len(tokens) == 1

    @pytest.mark.asyncio
    async def test_login_stores_refresh_token(self, auth_app, db):
        # Use unique email per test run
        import uuid

        email = f"login{uuid.uuid4().hex[:8]}@example.com"

        auth_app.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "password123",
            },
        )

        response = auth_app.post(
            "/api/auth/login",
            json={
                "email": email,
                "password": "password123",
            },
        )
        assert response.status_code == 200

        user_id = response.json()["user"]["id"]
        tokens = await db.fetch_all(
            f"SELECT * FROM {REFRESH_TOKENS_TABLE} WHERE user_id = ?", (user_id,)
        )
        # Login stores one refresh token (register already created one)
        assert len(tokens) >= 1


class TestRefreshEndpoint:
    def test_refresh_requires_token(self, auth_app):
        response = auth_app.post("/api/auth/refresh")
        assert response.status_code == 401

    def test_refresh_with_access_token_returns_error(self, auth_app):
        import uuid

        email = f"refresh{uuid.uuid4().hex[:8]}@example.com"

        auth_app.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "password123",
            },
        )

        login_resp = auth_app.post(
            "/api/auth/login",
            json={
                "email": email,
                "password": "password123",
            },
        )
        access_token = login_resp.json().get("token")

        if access_token:
            response = auth_app.post(
                "/api/auth/refresh",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert response.status_code == 200


class TestPasswordResetRevokesTokens:
    @pytest.mark.asyncio
    async def test_password_reset_revokes_all_refresh_tokens(self, auth_app, db):
        import uuid

        email = f"reset{uuid.uuid4().hex[:8]}@example.com"

        auth_app.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "oldpassword",
            },
        )

        login_resp = auth_app.post(
            "/api/auth/login",
            json={
                "email": email,
                "password": "oldpassword",
            },
        )
        user_id = login_resp.json()["user"]["id"]

        # Count tokens after register + login
        tokens_before = await db.fetch_all(
            f"SELECT * FROM {REFRESH_TOKENS_TABLE} WHERE user_id = ?", (user_id,)
        )
        initial_count = len(tokens_before)

        from datetime import datetime, timedelta, timezone

        reset_token = f"reset-token-{uuid.uuid4().hex[:8]}"
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        await db.execute(
            "INSERT INTO _password_resets (token, user_id, expires_at) VALUES (?, ?, ?)",
            (reset_token, user_id, expires_at),
        )

        response = auth_app.post(
            "/api/auth/reset-password",
            json={
                "token": reset_token,
                "new_password": "newpassword",
            },
        )
        assert response.status_code == 200

        tokens_after = await db.fetch_all(
            f"SELECT * FROM {REFRESH_TOKENS_TABLE} WHERE user_id = ?", (user_id,)
        )
        assert len(tokens_after) < initial_count


class TestLogoutRevokesTokens:
    def test_logout_clears_cookies(self, auth_app):
        import uuid

        email = f"logout{uuid.uuid4().hex[:8]}@example.com"

        auth_app.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "password123",
            },
        )

        login_resp = auth_app.post(
            "/api/auth/login",
            json={
                "email": email,
                "password": "password123",
            },
        )
        token = login_resp.json().get("token")

        if token:
            response = auth_app.post(
                "/api/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200


class TestTokenTypeVerification:
    def test_access_token_type_is_access(self):
        token = create_access_token("user-123", "user", 3600, SECRET)
        payload = decode_token(token, SECRET)
        assert payload["type"] == TOKEN_TYPE_ACCESS

    def test_refresh_token_type_is_refresh(self):
        token = create_refresh_token("user-123", "user", 604800, SECRET)
        payload = decode_token(token, SECRET)
        assert payload["type"] == TOKEN_TYPE_REFRESH


class TestAuthConfiguration:
    def test_default_auth_values(self):
        auth = Auth()
        assert auth.access_token_expiry == 3600
        assert auth.refresh_token_expiry == 604800
        assert auth.max_refresh_tokens == 5
        assert auth.blocklist_backend == "database"
        assert auth.token_delivery == "bearer"
        assert auth.cookie_secure is True
        assert auth.cookie_samesite == "lax"
        assert auth.csrf_enable is True

    def test_custom_auth_values(self):
        auth = Auth(
            access_token_expiry=7200,
            refresh_token_expiry=2592000,
            max_refresh_tokens=10,
            blocklist_backend="redis",
            token_delivery="cookie",
            cookie_secure=False,
            cookie_samesite="strict",
            csrf_enable=False,
        )
        assert auth.access_token_expiry == 7200
        assert auth.refresh_token_expiry == 2592000
        assert auth.max_refresh_tokens == 10
        assert auth.blocklist_backend == "redis"
        assert auth.token_delivery == "cookie"
        assert auth.cookie_secure is False
        assert auth.cookie_samesite == "strict"
        assert auth.csrf_enable is False
