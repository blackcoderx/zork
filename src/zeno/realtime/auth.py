from __future__ import annotations

import logging

from cinder.auth.models import USERS_TABLE, is_blocked
from cinder.auth.tokens import decode_token
from cinder.db.connection import Database
from cinder.errors import CinderError

logger = logging.getLogger("cinder.realtime.auth")


async def authenticate_ws_token(
    token: str,
    db: Database,
    secret: str,
) -> dict | None:
    """Decode a JWT token and return the user dict or ``None``.

    Used by both the WebSocket and SSE handlers because
    ``AuthMiddleware`` in ``pipeline.py`` only processes HTTP scopes.
    Unlike the middleware, this function raises ``CinderError`` so
    transport handlers can send a proper close/error response:

    - ``CinderError(401, ...)`` — invalid/expired token or blocked JTI
    - ``CinderError(401, "User not found")`` — valid token, missing user row

    Returns the user dict (without the ``password`` field) on success.
    """
    try:
        payload = decode_token(token, secret)
    except CinderError:
        raise

    jti = payload.get("jti")
    if jti and await is_blocked(db, jti):
        raise CinderError(401, "Token has been revoked")

    user_id = payload.get("sub")
    if not user_id:
        raise CinderError(401, "Invalid token payload")

    row = await db.fetch_one(
        f"SELECT * FROM {USERS_TABLE} WHERE id = ?", (user_id,)
    )
    if row is None:
        raise CinderError(401, "User not found")

    user = dict(row)
    user.pop("password", None)
    return user
