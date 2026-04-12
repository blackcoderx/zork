# Cinder API

[![PyPI version](https://img.shields.io/pypi/v/cinder?color=f47b20&label=cinder&style=flat-square)](https://pypi.org/project/cinder/)
[![Python](https://img.shields.io/pypi/pyversions/cinder?color=3572A5&style=flat-square)](https://pypi.org/project/cinder/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-cinderapi.vercel.app-f47b20?style=flat-square)](https://cinderapi.vercel.app)

A lightweight, open-source backend framework for Python. Define your data schema — Cinder auto-generates a full REST API with auth, CRUD, filtering, and more.

## Install

```bash
pip install cinder
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add cinder
```

**Optional extras:**

| Extra | What it adds |
|-------|-------------|
| `cinder[postgres]` | PostgreSQL support (asyncpg) |
| `cinder[mysql]` | MySQL support (aiomysql) |
| `cinder[s3]` | S3-compatible file storage (boto3) |
| `cinder[email]` | Email delivery (aiosmtplib) |
| `cinder[redis]` | Redis caching & sessions |
| `cinder[all]` | Everything above |

## Quick Start

```python
from cinder import Cinder, Collection, TextField, IntField, Auth

app = Cinder(database="app.db")

posts = Collection("posts", fields=[
    TextField("title", required=True),
    TextField("body"),
    IntField("views", default=0),
])

auth = Auth(token_expiry=86400, allow_registration=True)

app.register(posts, auth=["read:public", "write:authenticated"])
app.use_auth(auth)
app.serve()
```

```bash
cinder serve main.py
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
- Multi-database support — SQLite, PostgreSQL, MySQL
- Realtime via WebSocket and Server-Sent Events
- File storage — local filesystem or S3-compatible (AWS, R2, MinIO, and more)
- Lifecycle hooks — `before_create`, `after_update`, `before_delete`, etc.
- Built-in caching with in-memory or Redis backends
- Redis support — caching, sessions, and realtime pub/sub scaling
- Rate limiting per route
- Email delivery with SMTP and provider presets
- Schema migrations via CLI
- Auto-generated OpenAPI 3.1 + Swagger UI
- Zero boilerplate — one file to a working API

## Documentation

Full documentation at **[cinderapi.vercel.app](https://cinderapi.vercel.app)**

## License

[MIT](LICENSE)
