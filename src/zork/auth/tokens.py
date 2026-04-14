from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from jose import ExpiredSignatureError, JWTError, jwt

from zork.errors import ZorkError

ALGORITHM = "HS256"


def create_token(user_id: str, role: str, expiry: int, secret: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(seconds=expiry),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str, secret: str) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except ExpiredSignatureError:
        raise ZorkError(401, "Token has expired")
    except JWTError:
        raise ZorkError(401, "Invalid or expired token")
