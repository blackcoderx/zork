from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from cinder.auth import Auth
from cinder.auth.models import (
    USERS_TABLE, block_token, is_blocked, PASSWORD_RESETS_TABLE,
)
from cinder.auth.passwords import hash_password, verify_password
from cinder.auth.tokens import create_token, decode_token
from cinder.db.connection import Database
from cinder.errors import CinderError
from cinder.hooks.context import CinderContext


def _user_response(user: dict) -> dict:
    return {k: v for k, v in user.items() if k != "password"}


async def _get_current_user(request: Request, db: Database, secret: str):
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise CinderError(401, "Authentication required")

    token = auth_header[7:]
    payload = decode_token(token, secret)

    if await is_blocked(db, payload["jti"]):
        raise CinderError(401, "Token has been revoked")

    user = await db.fetch_one(
        f"SELECT * FROM {USERS_TABLE} WHERE id = ?", (payload["sub"],)
    )
    if user is None:
        raise CinderError(401, "User not found")

    return dict(user), payload


def build_auth_routes(auth: Auth, db: Database, secret: str) -> list[Route]:
    runner = auth._runner

    async def register(request: Request) -> JSONResponse:
        if not auth.allow_registration:
            raise CinderError(403, "Registration is disabled")

        body = await request.json()
        ctx = CinderContext.from_request(request, operation="register")
        body = await runner.run("auth:before_register", body, ctx)
        email = body.get("email")
        password = body.get("password")
        username = body.get("username")

        if not email or not password:
            raise CinderError(400, "Email and password are required")

        existing = await db.fetch_one(
            f"SELECT id FROM {USERS_TABLE} WHERE email = ?", (email,)
        )
        if existing:
            raise CinderError(400, "Email already registered")

        if username:
            existing_username = await db.fetch_one(
                f"SELECT id FROM {USERS_TABLE} WHERE username = ?", (username,)
            )
            if existing_username:
                raise CinderError(400, "Username already taken")

        now = datetime.now(timezone.utc).isoformat()
        user_id = str(uuid.uuid4())
        hashed = hash_password(password)

        columns = ["id", "email", "password", "is_verified", "is_active", "role", "created_at", "updated_at"]
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

        return JSONResponse(
            {"token": token, "user": user_dict},
            status_code=201,
        )

    async def login(request: Request) -> JSONResponse:
        body = await request.json()
        ctx = CinderContext.from_request(request, operation="login")
        body = await runner.run("auth:before_login", body, ctx)
        email = body.get("email")
        password = body.get("password")

        if not email or not password:
            raise CinderError(400, "Email and password are required")

        user = await db.fetch_one(
            f"SELECT * FROM {USERS_TABLE} WHERE email = ?", (email,)
        )
        if user is None:
            raise CinderError(401, "Invalid email or password")

        user = dict(user)
        if not verify_password(password, user["password"]):
            raise CinderError(401, "Invalid email or password")

        if not user["is_active"]:
            raise CinderError(403, "Account is disabled")

        token = create_token(user["id"], user["role"], auth.token_expiry, secret)
        user_resp = _user_response(user)
        await runner.run("auth:after_login", user_resp, ctx)
        return JSONResponse({"token": token, "user": user_resp})

    async def logout(request: Request) -> JSONResponse:
        user, payload = await _get_current_user(request, db, secret)
        ctx = CinderContext.from_request(request, operation="logout")
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
        ctx = CinderContext.from_request(request, operation="forgot_password")
        body = await runner.run("auth:before_password_reset", body, ctx)
        email = body.get("email")
        if not email:
            raise CinderError(400, "Email is required")

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
            logging.getLogger("cinder.auth").info(
                f"Password reset token for {email}: {reset_token}"
            )
            await runner.run("auth:after_password_reset", {"email": email, "user_id": user["id"]}, ctx)

        return JSONResponse({
            "message": "If the email exists, a reset link has been generated"
        })

    async def reset_password(request: Request) -> JSONResponse:
        body = await request.json()
        token = body.get("token")
        new_password = body.get("new_password")

        if not token or not new_password:
            raise CinderError(400, "Token and new_password are required")

        reset = await db.fetch_one(
            f"SELECT * FROM {PASSWORD_RESETS_TABLE} WHERE token = ?", (token,)
        )
        if reset is None:
            raise CinderError(400, "Invalid or expired reset token")

        reset = dict(reset)
        now = datetime.now(timezone.utc).isoformat()
        if reset["expires_at"] < now:
            await db.execute(
                f"DELETE FROM {PASSWORD_RESETS_TABLE} WHERE token = ?", (token,)
            )
            raise CinderError(400, "Invalid or expired reset token")

        hashed = hash_password(new_password)
        await db.execute(
            f"UPDATE {USERS_TABLE} SET password = ?, updated_at = ? WHERE id = ?",
            (hashed, now, reset["user_id"]),
        )
        await db.execute(
            f"DELETE FROM {PASSWORD_RESETS_TABLE} WHERE token = ?", (token,)
        )

        return JSONResponse({"message": "Password updated"})

    return [
        Route("/api/auth/register", register, methods=["POST"]),
        Route("/api/auth/login", login, methods=["POST"]),
        Route("/api/auth/logout", logout, methods=["POST"]),
        Route("/api/auth/me", me, methods=["GET"]),
        Route("/api/auth/refresh", refresh, methods=["POST"]),
        Route("/api/auth/forgot-password", forgot_password, methods=["POST"]),
        Route("/api/auth/reset-password", reset_password, methods=["POST"]),
    ]
