from __future__ import annotations

from datetime import datetime, timezone

from cinder.db.connection import Database

USERS_TABLE = "_users"
TOKEN_BLOCKLIST_TABLE = "_token_blocklist"
PASSWORD_RESETS_TABLE = "_password_resets"


async def create_auth_tables(db: Database, extend_columns: list[str] | None = None) -> None:
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


async def cleanup_expired_blocklist(db: Database) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        f"DELETE FROM {TOKEN_BLOCKLIST_TABLE} WHERE expires_at < ?", (now,)
    )


async def block_token(db: Database, jti: str, expires_at: str) -> None:
    await db.execute(
        f"INSERT OR IGNORE INTO {TOKEN_BLOCKLIST_TABLE} (jti, expires_at) VALUES (?, ?)",
        (jti, expires_at),
    )


async def is_blocked(db: Database, jti: str) -> bool:
    row = await db.fetch_one(
        f"SELECT jti FROM {TOKEN_BLOCKLIST_TABLE} WHERE jti = ?", (jti,)
    )
    return row is not None
