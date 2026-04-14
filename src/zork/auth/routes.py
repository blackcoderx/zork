from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from zork.auth import Auth
from zork.auth.models import (
    EMAIL_VERIFICATIONS_TABLE,
    PASSWORD_RESETS_TABLE,
    USERS_TABLE,
    block_token,
    create_verification_token,
    is_blocked,
)
from zork.auth.passwords import hash_password, verify_password
from zork.auth.tokens import create_token, decode_token
from zork.db.connection import Database
from zork.errors import ZorkError
from zork.hooks.context import ZorkContext


def _user_response(user: dict) -> dict:
    return {k: v for k, v in user.items() if k != "password"}


async def _get_current_user(request: Request, db: Database, secret: str):
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise ZorkError(401, "Authentication required")

    token = auth_header[7:]
    payload = decode_token(token, secret)

    if await is_blocked(db, payload["jti"]):
        raise ZorkError(401, "Token has been revoked")

    user = await db.fetch_one(
        f"SELECT * FROM {USERS_TABLE} WHERE id = ?", (payload["sub"],)
    )
    if user is None:
        raise ZorkError(401, "User not found")

    return dict(user), payload


def build_auth_routes(
    auth: Auth, db: Database, secret: str, email_config=None
) -> list[Route]:  # noqa: ANN001
    runner = auth._runner

    async def register(request: Request) -> JSONResponse:
        if not auth.allow_registration:
            raise ZorkError(403, "Registration is disabled")

        body = await request.json()
        ctx = ZorkContext.from_request(request, operation="register")
        body = await runner.run("auth:before_register", body, ctx)
        email = body.get("email")
        password = body.get("password")
        username = body.get("username")

        if not email or not password:
            raise ZorkError(400, "Email and password are required")

        existing = await db.fetch_one(
            f"SELECT id FROM {USERS_TABLE} WHERE email = ?", (email,)
        )
        if existing:
            raise ZorkError(400, "Email already registered")

        if username:
            existing_username = await db.fetch_one(
                f"SELECT id FROM {USERS_TABLE} WHERE username = ?", (username,)
            )
            if existing_username:
                raise ZorkError(400, "Username already taken")

        now = datetime.now(timezone.utc).isoformat()
        user_id = str(uuid.uuid4())
        hashed = hash_password(password)

        columns = [
            "id",
            "email",
            "password",
            "is_verified",
            "is_active",
            "role",
            "created_at",
            "updated_at",
        ]
        values = [user_id, email, hashed, 0, 1, "user", now, now]

        if username:
            columns.append("username")
            values.append(username)

        for field in auth.extend_user:
            if field.name in body:
                columns.append(field.name)
                values.append(body[field.name])

        col_str = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)
        await db.execute(
            f"INSERT INTO {USERS_TABLE} ({col_str}) VALUES ({placeholders})",
            tuple(values),
        )

        token = create_token(user_id, "user", auth.token_expiry, secret)
        user = await db.fetch_one(
            f"SELECT * FROM {USERS_TABLE} WHERE id = ?", (user_id,)
        )
        user_dict = _user_response(dict(user))
        await runner.run("auth:after_register", user_dict, ctx)

        # Send email verification link (non-blocking; silent if no backend configured)
        if email_config is not None:
            from zork.email.backends import EmailMessage
            from zork.email.templates import email_verification_email

            ver_token = await create_verification_token(db, user_id, email)
            verify_url = (
                f"{email_config._base_url}/api/auth/verify-email?token={ver_token}"
            )
            subject, html, text = email_config._render_verification(verify_url)
            await email_config.send(
                EmailMessage(to=email, subject=subject, html_body=html, text_body=text)
            )

        return JSONResponse(
            {"token": token, "user": user_dict},
            status_code=201,
        )

    async def login(request: Request) -> JSONResponse:
        body = await request.json()
        ctx = ZorkContext.from_request(request, operation="login")
        body = await runner.run("auth:before_login", body, ctx)
        email = body.get("email")
        password = body.get("password")

        if not email or not password:
            raise ZorkError(400, "Email and password are required")

        user = await db.fetch_one(
            f"SELECT * FROM {USERS_TABLE} WHERE email = ?", (email,)
        )
        if user is None:
            raise ZorkError(401, "Invalid email or password")

        user = dict(user)
        if not verify_password(password, user["password"]):
            raise ZorkError(401, "Invalid email or password")

        if not user["is_active"]:
            raise ZorkError(403, "Account is disabled")

        token = create_token(user["id"], user["role"], auth.token_expiry, secret)
        user_resp = _user_response(user)
        await runner.run("auth:after_login", user_resp, ctx)
        return JSONResponse({"token": token, "user": user_resp})

    async def logout(request: Request) -> JSONResponse:
        user, payload = await _get_current_user(request, db, secret)
        ctx = ZorkContext.from_request(request, operation="logout")
        user_resp = _user_response(user)
        await runner.run("auth:before_logout", user_resp, ctx)
        exp = payload.get("exp", "")
        expires_at = (
            datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
            if isinstance(exp, (int, float))
            else str(exp)
        )
        await block_token(db, payload["jti"], expires_at)
        await runner.run("auth:after_logout", user_resp, ctx)
        return JSONResponse({"message": "Logged out"})

    async def me(request: Request) -> JSONResponse:
        user, _ = await _get_current_user(request, db, secret)
        return JSONResponse(_user_response(user))

    async def refresh(request: Request) -> JSONResponse:
        user, payload = await _get_current_user(request, db, secret)
        exp = payload.get("exp", "")
        expires_at = (
            datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
            if isinstance(exp, (int, float))
            else str(exp)
        )
        await block_token(db, payload["jti"], expires_at)
        new_token = create_token(user["id"], user["role"], auth.token_expiry, secret)
        return JSONResponse({"token": new_token})

    async def forgot_password(request: Request) -> JSONResponse:
        body = await request.json()
        ctx = ZorkContext.from_request(request, operation="forgot_password")
        body = await runner.run("auth:before_password_reset", body, ctx)
        email = body.get("email")
        if not email:
            raise ZorkError(400, "Email is required")

        user = await db.fetch_one(
            f"SELECT id FROM {USERS_TABLE} WHERE email = ?", (email,)
        )
        if user:
            user = dict(user)
            reset_token = str(uuid.uuid4())
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            await db.execute(
                f"INSERT INTO {PASSWORD_RESETS_TABLE} (token, user_id, expires_at) VALUES (?, ?, ?)",
                (reset_token, user["id"], expires_at),
            )
            if email_config is not None:
                from zork.email.backends import EmailMessage

                reset_url = (
                    f"{email_config._base_url}/reset-password?token={reset_token}"
                )
                subject, html, text = email_config._render_password_reset(reset_url)
                await email_config.send(
                    EmailMessage(
                        to=email, subject=subject, html_body=html, text_body=text
                    )
                )
            else:
                logging.getLogger("zork.auth").info(
                    "Password reset token for %s: %s", email, reset_token
                )
            await runner.run(
                "auth:after_password_reset",
                {"email": email, "user_id": user["id"]},
                ctx,
            )

        return JSONResponse(
            {"message": "If the email exists, a reset link has been generated"}
        )

    async def reset_password(request: Request) -> JSONResponse:
        body = await request.json()
        token = body.get("token")
        new_password = body.get("new_password")

        if not token or not new_password:
            raise ZorkError(400, "Token and new_password are required")

        reset = await db.fetch_one(
            f"SELECT * FROM {PASSWORD_RESETS_TABLE} WHERE token = ?", (token,)
        )
        if reset is None:
            raise ZorkError(400, "Invalid or expired reset token")

        reset = dict(reset)
        now = datetime.now(timezone.utc).isoformat()
        if reset["expires_at"] < now:
            await db.execute(
                f"DELETE FROM {PASSWORD_RESETS_TABLE} WHERE token = ?", (token,)
            )
            raise ZorkError(400, "Invalid or expired reset token")

        hashed = hash_password(new_password)
        await db.execute(
            f"UPDATE {USERS_TABLE} SET password = ?, updated_at = ? WHERE id = ?",
            (hashed, now, reset["user_id"]),
        )
        await db.execute(
            f"DELETE FROM {PASSWORD_RESETS_TABLE} WHERE token = ?", (token,)
        )

        return JSONResponse({"message": "Password updated"})

    async def verify_email(request: Request) -> JSONResponse:
        token = request.query_params.get("token")
        if not token:
            raise ZorkError(400, "Verification token is required")

        row = await db.fetch_one(
            f"SELECT * FROM {EMAIL_VERIFICATIONS_TABLE} WHERE token = ?", (token,)
        )
        if row is None:
            raise ZorkError(400, "Invalid or expired verification token")

        row = dict(row)
        now = datetime.now(timezone.utc).isoformat()
        if row["expires_at"] < now:
            await db.execute(
                f"DELETE FROM {EMAIL_VERIFICATIONS_TABLE} WHERE token = ?", (token,)
            )
            raise ZorkError(400, "Invalid or expired verification token")

        await db.execute(
            f"UPDATE {USERS_TABLE} SET is_verified = 1, updated_at = ? WHERE id = ?",
            (now, row["user_id"]),
        )
        await db.execute(
            f"DELETE FROM {EMAIL_VERIFICATIONS_TABLE} WHERE token = ?", (token,)
        )

        ctx = ZorkContext.from_request(request, operation="verify_email")
        await runner.run(
            "auth:after_verify_email",
            {"user_id": row["user_id"], "email": row["email"]},
            ctx,
        )
        return JSONResponse({"message": "Email verified successfully"})

    return [
        Route("/api/auth/register", register, methods=["POST"]),
        Route("/api/auth/login", login, methods=["POST"]),
        Route("/api/auth/logout", logout, methods=["POST"]),
        Route("/api/auth/me", me, methods=["GET"]),
        Route("/api/auth/refresh", refresh, methods=["POST"]),
        Route("/api/auth/forgot-password", forgot_password, methods=["POST"]),
        Route("/api/auth/reset-password", reset_password, methods=["POST"]),
        Route("/api/auth/verify-email", verify_email, methods=["GET"]),
    ]
