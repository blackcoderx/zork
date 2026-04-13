"""Integration tests for the email verification flow.

Tests cover:
- POST /api/auth/register → token inserted into _email_verifications when email_config set
- GET /api/auth/verify-email?token=<valid> → is_verified=1, token deleted
- GET /api/auth/verify-email?token=<used-or-missing> → 400
- GET /api/auth/verify-email?token=<expired> → 400
- Forgot-password: console log fires when email_config=None (existing behaviour preserved)
- All existing auth routes still work with email_config=None (non-breaking)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from zeno.auth import Auth
from zeno.auth.models import (
    EMAIL_VERIFICATIONS_TABLE,
    USERS_TABLE,
    create_auth_tables,
    create_verification_token,
)
from zeno.auth.routes import build_auth_routes
from zeno.db.connection import Database
from zeno.pipeline import build_middleware_stack

SECRET = "test-secret-email-verification"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_email_config(send_mock=None):
    """Create a minimal _EmailConfig-like object for testing."""
    from zeno.app import _EmailConfig

    cfg = _EmailConfig()
    cfg.configure(
        from_address="no-reply@test.com",
        app_name="TestApp",
        base_url="http://localhost:8000",
    )
    if send_mock is not None:
        cfg.send = send_mock
    return cfg


@pytest.fixture
async def db_with_auth(db_path):
    db = Database(db_path)
    await db.connect()
    await create_auth_tables(db)
    yield db
    await db.disconnect()


def _build_test_app(db, auth, email_config=None):
    routes = build_auth_routes(auth, db, SECRET, email_config=email_config)
    app = Starlette(routes=routes)
    return build_middleware_stack(app)


# ---------------------------------------------------------------------------
# Without email_config — non-breaking backward compatibility
# ---------------------------------------------------------------------------


class TestNoEmailConfig:
    @pytest.mark.asyncio
    async def test_register_works_without_email_config(self, db_with_auth):
        auth = Auth(allow_registration=True)
        app = _build_test_app(db_with_auth, auth, email_config=None)
        client = TestClient(app)

        resp = client.post("/api/auth/register", json={
            "email": "user@example.com",
            "password": "password123",
        })
        assert resp.status_code == 201
        assert "token" in resp.json()

    @pytest.mark.asyncio
    async def test_login_works_without_email_config(self, db_with_auth):
        auth = Auth(allow_registration=True)
        app = _build_test_app(db_with_auth, auth, email_config=None)
        client = TestClient(app)

        client.post("/api/auth/register", json={
            "email": "user@example.com", "password": "pass123",
        })
        resp = client.post("/api/auth/login", json={
            "email": "user@example.com", "password": "pass123",
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_forgot_password_logs_when_no_email_config(self, db_with_auth, caplog):
        """Forgot-password should fall back to logger.info when email_config=None."""
        import logging
        auth = Auth(allow_registration=True)
        app = _build_test_app(db_with_auth, auth, email_config=None)
        client = TestClient(app)

        # Register a user first
        client.post("/api/auth/register", json={
            "email": "reset@example.com", "password": "pass123",
        })

        with caplog.at_level(logging.INFO, logger="zeno.auth"):
            resp = client.post("/api/auth/forgot-password", json={"email": "reset@example.com"})

        assert resp.status_code == 200
        # The reset token should have been logged
        combined = "\n".join(caplog.messages)
        assert "reset" in combined.lower() or "token" in combined.lower()


# ---------------------------------------------------------------------------
# With email_config — email dispatch + verification flow
# ---------------------------------------------------------------------------


class TestWithEmailConfig:
    @pytest.mark.asyncio
    async def test_register_creates_verification_token(self, db_with_auth):
        """After registration with email_config, a token is inserted in _email_verifications."""
        sent_messages = []

        async def capture_send(msg):
            sent_messages.append(msg)

        cfg = _make_email_config(send_mock=capture_send)
        auth = Auth(allow_registration=True)
        app = _build_test_app(db_with_auth, auth, email_config=cfg)
        client = TestClient(app)

        resp = client.post("/api/auth/register", json={
            "email": "newuser@example.com",
            "password": "password123",
        })
        assert resp.status_code == 201

        # Allow any pending tasks to complete
        import asyncio
        await asyncio.sleep(0)

        # Verify token was stored in DB
        row = await db_with_auth.fetch_one(
            f"SELECT * FROM {EMAIL_VERIFICATIONS_TABLE} WHERE email = ?",
            ("newuser@example.com",),
        )
        assert row is not None
        row = dict(row)
        assert row["email"] == "newuser@example.com"
        assert row["token"] is not None

    @pytest.mark.asyncio
    async def test_register_user_is_not_verified_initially(self, db_with_auth):
        """Newly registered user has is_verified=0."""
        cfg = _make_email_config(send_mock=AsyncMock())
        auth = Auth(allow_registration=True)
        app = _build_test_app(db_with_auth, auth, email_config=cfg)
        client = TestClient(app)

        resp = client.post("/api/auth/register", json={
            "email": "unverified@example.com",
            "password": "password123",
        })
        assert resp.status_code == 201
        user_id = resp.json()["user"]["id"]

        row = await db_with_auth.fetch_one(
            f"SELECT is_verified FROM {USERS_TABLE} WHERE id = ?", (user_id,)
        )
        assert dict(row)["is_verified"] == 0


class TestVerifyEmailEndpoint:
    @pytest.mark.asyncio
    async def test_verify_email_sets_is_verified(self, db_with_auth):
        """GET /api/auth/verify-email?token=<valid> flips is_verified to 1."""
        auth = Auth(allow_registration=True)
        app = _build_test_app(db_with_auth, auth)
        client = TestClient(app)

        # Create a user
        resp = client.post("/api/auth/register", json={
            "email": "verify@example.com", "password": "pw123",
        })
        user_id = resp.json()["user"]["id"]

        # Insert a valid verification token directly
        token = await create_verification_token(db_with_auth, user_id, "verify@example.com")

        resp = client.get(f"/api/auth/verify-email?token={token}")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Email verified successfully"

        # Confirm is_verified=1 in DB
        row = await db_with_auth.fetch_one(
            f"SELECT is_verified FROM {USERS_TABLE} WHERE id = ?", (user_id,)
        )
        assert dict(row)["is_verified"] == 1

    @pytest.mark.asyncio
    async def test_verify_email_deletes_token(self, db_with_auth):
        """Token is removed after successful verification (one-time use)."""
        auth = Auth(allow_registration=True)
        app = _build_test_app(db_with_auth, auth)
        client = TestClient(app)

        resp = client.post("/api/auth/register", json={
            "email": "once@example.com", "password": "pw123",
        })
        user_id = resp.json()["user"]["id"]
        token = await create_verification_token(db_with_auth, user_id, "once@example.com")

        client.get(f"/api/auth/verify-email?token={token}")

        row = await db_with_auth.fetch_one(
            f"SELECT token FROM {EMAIL_VERIFICATIONS_TABLE} WHERE token = ?", (token,)
        )
        assert row is None

    @pytest.mark.asyncio
    async def test_verify_email_invalid_token_returns_400(self, db_with_auth):
        """Unknown token → 400."""
        auth = Auth(allow_registration=True)
        app = _build_test_app(db_with_auth, auth)
        client = TestClient(app)

        resp = client.get("/api/auth/verify-email?token=totally-fake-token")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_verify_email_missing_token_returns_400(self, db_with_auth):
        """No token query param → 400."""
        auth = Auth(allow_registration=True)
        app = _build_test_app(db_with_auth, auth)
        client = TestClient(app)

        resp = client.get("/api/auth/verify-email")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_verify_email_already_used_returns_400(self, db_with_auth):
        """Using the same token twice → 400 on second use."""
        auth = Auth(allow_registration=True)
        app = _build_test_app(db_with_auth, auth)
        client = TestClient(app)

        resp = client.post("/api/auth/register", json={
            "email": "twice@example.com", "password": "pw123",
        })
        user_id = resp.json()["user"]["id"]
        token = await create_verification_token(db_with_auth, user_id, "twice@example.com")

        # First use — ok
        r1 = client.get(f"/api/auth/verify-email?token={token}")
        assert r1.status_code == 200

        # Second use — token already deleted
        r2 = client.get(f"/api/auth/verify-email?token={token}")
        assert r2.status_code == 400

    @pytest.mark.asyncio
    async def test_verify_email_expired_token_returns_400(self, db_with_auth):
        """Expired token → 400 and token is cleaned up."""
        auth = Auth(allow_registration=True)
        app = _build_test_app(db_with_auth, auth)
        client = TestClient(app)

        resp = client.post("/api/auth/register", json={
            "email": "expired@example.com", "password": "pw123",
        })
        user_id = resp.json()["user"]["id"]

        # Insert an already-expired token directly
        expired_token = str(uuid.uuid4())
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        await db_with_auth.execute(
            f"INSERT INTO {EMAIL_VERIFICATIONS_TABLE} "
            "(token, user_id, email, expires_at) VALUES (?, ?, ?, ?)",
            (expired_token, user_id, "expired@example.com", past),
        )

        resp = client.get(f"/api/auth/verify-email?token={expired_token}")
        assert resp.status_code == 400

        # Token should be cleaned up
        row = await db_with_auth.fetch_one(
            f"SELECT token FROM {EMAIL_VERIFICATIONS_TABLE} WHERE token = ?",
            (expired_token,),
        )
        assert row is None


# ---------------------------------------------------------------------------
# Forgot-password with email_config
# ---------------------------------------------------------------------------


class TestForgotPasswordWithEmail:
    @pytest.mark.asyncio
    async def test_forgot_password_dispatches_email(self, db_with_auth):
        """When email_config is set, forgot-password calls email_config.send()."""
        sent = []

        async def capture(msg):
            sent.append(msg)

        cfg = _make_email_config(send_mock=capture)
        auth = Auth(allow_registration=True)
        app = _build_test_app(db_with_auth, auth, email_config=cfg)
        client = TestClient(app)

        # Register first
        client.post("/api/auth/register", json={
            "email": "forgot@example.com", "password": "pw123",
        })

        resp = client.post("/api/auth/forgot-password", json={"email": "forgot@example.com"})
        assert resp.status_code == 200

        # Allow any scheduled coroutine to run
        import asyncio
        await asyncio.sleep(0)

        assert len(sent) >= 1
        assert sent[0].to == "forgot@example.com"

    @pytest.mark.asyncio
    async def test_forgot_password_unknown_email_still_200(self, db_with_auth):
        """Should always return 200 (prevent email enumeration)."""
        cfg = _make_email_config(send_mock=AsyncMock())
        auth = Auth(allow_registration=True)
        app = _build_test_app(db_with_auth, auth, email_config=cfg)
        client = TestClient(app)

        resp = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# create_verification_token helper
# ---------------------------------------------------------------------------


class TestCreateVerificationToken:
    @pytest.mark.asyncio
    async def test_returns_token_string(self, db_with_auth):
        token = await create_verification_token(db_with_auth, "user-1", "a@ex.com")
        assert isinstance(token, str)
        assert len(token) > 0

    @pytest.mark.asyncio
    async def test_token_is_unique_per_call(self, db_with_auth):
        t1 = await create_verification_token(db_with_auth, "user-2", "b@ex.com")
        t2 = await create_verification_token(db_with_auth, "user-3", "c@ex.com")
        assert t1 != t2

    @pytest.mark.asyncio
    async def test_insert_or_replace_invalidates_old_token(self, db_with_auth):
        """Calling create_verification_token twice for the same user replaces the old token."""
        t1 = await create_verification_token(db_with_auth, "user-4", "d@ex.com")
        t2 = await create_verification_token(db_with_auth, "user-4", "d@ex.com")

        # Old token must be gone
        row = await db_with_auth.fetch_one(
            f"SELECT token FROM {EMAIL_VERIFICATIONS_TABLE} WHERE token = ?", (t1,)
        )
        assert row is None

        # New token must exist
        row2 = await db_with_auth.fetch_one(
            f"SELECT token FROM {EMAIL_VERIFICATIONS_TABLE} WHERE token = ?", (t2,)
        )
        assert row2 is not None
