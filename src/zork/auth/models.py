from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone

from zork.db.backends.base import DatabaseIntegrityError
from zork.db.connection import Database

VALID_IDENTIFIER = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

USERS_TABLE = "_users"
TOKEN_BLOCKLIST_TABLE = "_token_blocklist"
REFRESH_TOKENS_TABLE = "_refresh_tokens"
PASSWORD_RESETS_TABLE = "_password_resets"
EMAIL_VERIFICATIONS_TABLE = "_email_verifications"


def _validate_column_name(name: str) -> str:
    """Validate column name to prevent SQL injection.

    Column names must match SQL identifier rules.
    """
    if not VALID_IDENTIFIER.match(name):
        raise ValueError(f"Invalid column name: {name}")
    return name


async def create_auth_tables(
    db: Database, extend_columns: list[str] | None = None
) -> None:
    extra_cols = ""
    if extend_columns:
        validated_cols = [_validate_column_name(c) for c in extend_columns]
        extra_cols = ", " + ", ".join(validated_cols)

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
        CREATE TABLE IF NOT EXISTS {REFRESH_TOKENS_TABLE} (
            jti_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES {USERS_TABLE}(id)
        )
    """)

    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS {PASSWORD_RESETS_TABLE} (
            token TEXT NOT NULL,
            user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            lookup TEXT NOT NULL,
            PRIMARY KEY (lookup)
        )
    """)
    await db.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_password_resets_user 
        ON {PASSWORD_RESETS_TABLE}(user_id)
    """)

    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS {EMAIL_VERIFICATIONS_TABLE} (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            email TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)

    await db.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user 
        ON {REFRESH_TOKENS_TABLE}(user_id, created_at)
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


async def create_password_reset_token(db: Database, user_id: str, email: str) -> str:
    """Insert a new 1-hour password reset token (hashed in DB).

    Any prior tokens for the same ``user_id`` are deleted first.

    Returns the raw token string (sent to user), not the hash.
    """
    token = str(uuid.uuid4())
    token_hash = hash_jti(token)
    lookup = hash_jti(token + email)  # token + email order for lookup
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    await db.execute(
        f"DELETE FROM {PASSWORD_RESETS_TABLE} WHERE user_id = ?", (user_id,)
    )
    await db.execute(
        f"INSERT INTO {PASSWORD_RESETS_TABLE} "
        "(token, user_id, expires_at, lookup) VALUES (?, ?, ?, ?)",
        (token_hash, user_id, expires_at, lookup),
    )
    return token


async def verify_password_reset_token(db: Database, email: str, token: str) -> bool:
    """Verify a password reset token.

    Uses lookup key for efficient verification.
    Returns True if valid and not expired.
    """
    lookup = hash_jti(token + email)
    row = await db.fetch_one(
        f"SELECT * FROM {PASSWORD_RESETS_TABLE} WHERE lookup = ?",
        (lookup,),
    )
    if row is None:
        return False
    now = datetime.now(timezone.utc).isoformat()
    if row["expires_at"] < now:
        return False
    return True


async def delete_password_reset_token(db: Database, email: str, token: str) -> None:
    """Delete a password reset token after use."""
    lookup = hash_jti(token + email)
    await db.execute(
        f"DELETE FROM {PASSWORD_RESETS_TABLE} WHERE lookup = ?",
        (lookup,),
    )


async def lookup_password_reset_token(db: Database, email: str, token: str) -> dict | None:
    """Look up a password reset token by email and raw token."""
    lookup = hash_jti(token + email)  # token + email order
    row = await db.fetch_one(
        f"SELECT * FROM {PASSWORD_RESETS_TABLE} WHERE lookup = ?",
        (lookup,),
    )
    return dict(row) if row else None


async def get_password_reset_user_id(db: Database, email: str, token: str) -> str | None:
    """Get user_id from password reset token."""
    reset = await lookup_password_reset_token(db, email, token)
    return reset["user_id"] if reset else None


async def cleanup_expired_verifications(db: Database) -> None:
    """Delete expired email verification tokens. Called at startup."""
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        f"DELETE FROM {EMAIL_VERIFICATIONS_TABLE} WHERE expires_at < ?", (now,)
    )


def hash_jti(jti: str) -> str:
    """Hash a JTI using SHA256 for secure storage."""
    return hashlib.sha256(jti.encode()).hexdigest()


async def store_refresh_token(
    db: Database, user_id: str, jti: str, expires_in: int
) -> None:
    """Store a refresh token hash for a user.

    Args:
        db: Database connection.
        user_id: The user's ID.
        jti: The JWT ID (jti claim) of the refresh token.
        expires_in: Seconds until token expiration.
    """
    jti_hash = hash_jti(jti)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(seconds=expires_in)).isoformat()
    created_at = now.isoformat()

    try:
        await db.execute(
            f"INSERT INTO {REFRESH_TOKENS_TABLE} "
            "(jti_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (jti_hash, user_id, expires_at, created_at),
        )
    except DatabaseIntegrityError:
        pass


async def get_refresh_token_by_jti(db: Database, jti: str) -> dict | None:
    """Look up a refresh token by its JTI hash.

    Args:
        db: Database connection.
        jti: The JWT ID (jti claim) of the refresh token.

    Returns:
        The stored token record (with hashed jti) or None if not found.
    """
    jti_hash = hash_jti(jti)
    row = await db.fetch_one(
        f"SELECT * FROM {REFRESH_TOKENS_TABLE} WHERE jti_hash = ?", (jti_hash,)
    )
    return dict(row) if row else None


async def delete_refresh_token(db: Database, jti: str) -> None:
    """Delete a specific refresh token by JTI.

    Args:
        db: Database connection.
        jti: The JWT ID (jti claim) of the refresh token to delete.
    """
    jti_hash = hash_jti(jti)
    await db.execute(
        f"DELETE FROM {REFRESH_TOKENS_TABLE} WHERE jti_hash = ?", (jti_hash,)
    )


async def revoke_all_user_refresh_tokens(db: Database, user_id: str) -> None:
    """Revoke all refresh tokens for a user.

    Used when password is changed or account needs full logout.

    Args:
        db: Database connection.
        user_id: The user's ID.
    """
    await db.execute(
        f"DELETE FROM {REFRESH_TOKENS_TABLE} WHERE user_id = ?", (user_id,)
    )


async def enforce_refresh_token_limit(
    db: Database, user_id: str, max_tokens: int
) -> int:
    """Enforce maximum refresh tokens per user.

    Deletes oldest tokens if the limit is exceeded.

    Args:
        db: Database connection.
        user_id: The user's ID.
        max_tokens: Maximum allowed tokens per user.

    Returns:
        Number of tokens deleted.
    """
    row = await db.fetch_one(
        f"SELECT COUNT(*) as cnt FROM {REFRESH_TOKENS_TABLE} WHERE user_id = ?",
        (user_id,),
    )
    count = row["cnt"] if row else 0

    if count >= max_tokens:
        excess = count - max_tokens + 1
        await db.execute(
            f"""
            DELETE FROM {REFRESH_TOKENS_TABLE} 
            WHERE user_id = ? AND jti_hash IN (
                SELECT jti_hash FROM {REFRESH_TOKENS_TABLE} 
                WHERE user_id = ? ORDER BY created_at ASC LIMIT ?
            )
            """,
            (user_id, user_id, excess),
        )
        return excess
    return 0


async def cleanup_expired_refresh_tokens(db: Database) -> None:
    """Delete expired refresh tokens. Called at startup."""
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(f"DELETE FROM {REFRESH_TOKENS_TABLE} WHERE expires_at < ?", (now,))
