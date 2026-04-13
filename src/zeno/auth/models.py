from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from zeno.db.backends.base import DatabaseIntegrityError
from zeno.db.connection import Database

USERS_TABLE = "_users"
TOKEN_BLOCKLIST_TABLE = "_token_blocklist"
PASSWORD_RESETS_TABLE = "_password_resets"
EMAIL_VERIFICATIONS_TABLE = "_email_verifications"


async def create_auth_tables(
    db: Database, extend_columns: list[str] | None = None
) -> None:
    extra_cols = ""
    if extend_columns:
        extra_cols = ", " + ", ".join(extend_columns)

    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS {USERS_TABLE} (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE,
            password TEXT NOT NULL,
            is_verified INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            role TEXT DEFAULT 'user',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL{extra_cols}
        )
    """)

    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS {TOKEN_BLOCKLIST_TABLE} (
            jti TEXT PRIMARY KEY,
            expires_at TEXT NOT NULL
        )
    """)

    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS {PASSWORD_RESETS_TABLE} (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)

    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS {EMAIL_VERIFICATIONS_TABLE} (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            email TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)


async def cleanup_expired_blocklist(db: Database) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        f"DELETE FROM {TOKEN_BLOCKLIST_TABLE} WHERE expires_at < ?", (now,)
    )


async def block_token(db: Database, jti: str, expires_at: str) -> None:
    """Add a JWT to the blocklist. Idempotent — safe to call multiple times."""
    try:
        await db.execute(
            f"INSERT INTO {TOKEN_BLOCKLIST_TABLE} (jti, expires_at) VALUES (?, ?)",
            (jti, expires_at),
        )
    except DatabaseIntegrityError:
        # Token already blocked — idempotent, safe to ignore.
        pass


async def is_blocked(db: Database, jti: str) -> bool:
    row = await db.fetch_one(
        f"SELECT jti FROM {TOKEN_BLOCKLIST_TABLE} WHERE jti = ?", (jti,)
    )
    return row is not None


async def create_verification_token(db: Database, user_id: str, email: str) -> str:
    """Insert a new 24-hour email verification token.

    Any prior tokens for the same ``user_id`` are deleted first, so
    re-sending a verification email automatically invalidates the old link.

    Returns the token string.
    """
    token = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    # Delete any existing token for this user before inserting the new one.
    await db.execute(
        f"DELETE FROM {EMAIL_VERIFICATIONS_TABLE} WHERE user_id = ?", (user_id,)
    )
    await db.execute(
        f"INSERT INTO {EMAIL_VERIFICATIONS_TABLE} "
        "(token, user_id, email, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, email, expires_at),
    )
    return token


async def cleanup_expired_verifications(db: Database) -> None:
    """Delete expired email verification tokens. Called at startup."""
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        f"DELETE FROM {EMAIL_VERIFICATIONS_TABLE} WHERE expires_at < ?", (now,)
    )
