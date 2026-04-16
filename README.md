# Zork

<p align="center">

[![PyPI version](https://img.shields.io/pypi/v/zork?color=f47b20&label=zork&style=flat-square)](https://pypi.org/project/zork/)
[![Python](https://img.shields.io/pypi/pyversions/zork?color=3572A5&style=flat-square)](https://pypi.org/project/zork/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-zork.vercel.app-f47b20?style=flat-square)](https://zork.vercel.app)

</p>

A lightweight, open-source backend framework for Python. Define your data schema — Zork auto-generates a full REST API with auth, CRUD, filtering, and more.

## Install

```bash
pip install zork
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add zork
```

**Optional extras:**

| Extra | What it adds |
|-------|-------------|
| `zork[postgres]` | PostgreSQL support (asyncpg) |
| `zork[mysql]` | MySQL support (aiomysql) |
| `zork[s3]` | S3-compatible file storage (boto3) |
| `zork[email]` | Email delivery (aiosmtplib) |
| `zork[redis]` | Redis caching & sessions |
| `zork[all]` | Everything above |

## Quick Start

```python
from zork import Zork, Collection, TextField, IntField, Auth

app = Zork(database="app.db")

posts = Collection("posts", fields=[
    TextField("title", required=True),
    TextField("body"),
    IntField("views", default=0),
])

# === Session Style (HTTP-Only Cookies + Redis Blocklist) ===
# Use for: Web apps, SSR, browser-based clients
# - Tokens stored in HTTP-only cookies (XSS resistant)
# - CSRF protection via double-submit cookie
# - Fast token revocation with Redis TTL
auth = Auth(
    delivery="cookie",
    blocklist_backend="redis",
    token_expiry=3600,
    refresh_token_expiry=604800,
    cookie_secure=True,
    cookie_samesite="lax",
    csrf_enabled=True,
    max_refresh_tokens=5,
    allow_registration=True,
)

# === API Style (Bearer Token) ===
# Use for: Mobile apps, third-party APIs, SPAs
# - Tokens returned in JSON response
# - Store in localStorage/sessionStorage (manual)
# - Attach Authorization header manually
# auth = Auth(
#     delivery="bearer",
#     blocklist_backend="redis",
#     token_expiry=3600,
#     refresh_token_expiry=604800,
#     allow_registration=True,
# )

app.register(posts, auth=["read:public", "write:authenticated"])
app.use_auth(auth)
app.serve()
```

```bash
zork serve main.py
# Server running at http://localhost:8000
```

You now have:

- `POST /api/auth/register` — register users
- `POST /api/auth/login` — get a JWT token
- `GET /api/posts` — list posts (public)
- `POST /api/posts` — create a post (requires auth)
- `GET /api/posts/{id}` — get a single post
- `PATCH /api/posts/{id}` — update a post
- `DELETE /api/posts/{id}` — delete a post
- `GET /openapi.json` — OpenAPI 3.1 schema
- `GET /docs` — Swagger UI

## Features

- Auto-generated CRUD REST API from Python schemas
- JWT authentication with role-based access control
- HTTP-only cookie delivery with CSRF protection
- Refresh token rotation with automatic blocklist (Redis or database)
- Multi-database support — SQLite, PostgreSQL, MySQL
- Realtime via WebSocket and Server-Sent Events
- File storage — local filesystem or S3-compatible (AWS, R2, MinIO, and more)
- Lifecycle hooks — `before_create`, `after_update`, `before_delete`, etc.
- Built-in caching with in-memory or Redis backends
- Redis support — caching, sessions, and realtime pub/sub scaling
- Rate limiting per route
- Email delivery with SMTP and provider presets
- Schema migrations via CLI
- One-command deployment — generate Docker, Railway, Render, and Fly.io configs with `zork deploy`
- Auto-generated OpenAPI 3.1 + Swagger UI
- Zero boilerplate — one file to a working API

## Documentation

Full documentation at **[docs](https://github.com/blackcoderx/zork/tree/main/docs)**

## License

[MIT](LICENSE)
