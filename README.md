# Zork

<p align="center">

[![PyPI version](https://img.shields.io/pypi/v/zork?color=f47b20&label=zork&style=flat-square)](https://pypi.org/project/zork/)
[![CI](https://github.com/blackcoderx/zork/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/blackcoderx/zork/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/zork?color=3572A5&style=flat-square)](https://pypi.org/project/zork/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-zork.vercel.app-f47b20?style=flat-square)](https://zork.vercel.app)

</p>

Define your data schema — Zork auto-generates a production-ready REST API with authentication, file storage, caching, realtime support, and more. No boilerplate. No configuration files. Just Python.

## Install

```bash
pip install zork
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add zork
```

**Optional extras:**

| Extra | Installs |
|-------|----------|
| `zork[postgres]` | PostgreSQL support via asyncpg |
| `zork[mysql]` | MySQL support via aiomysql |
| `zork[s3]` | S3-compatible storage via boto3 |
| `zork[email]` | Email delivery via aiosmtplib |
| `zork[redis]` | Redis for caching, sessions, and realtime |
| `zork[all]` | All of the above |

## Quick Start

```python
from zork import Zork, Collection, TextField, IntField, BoolField, Auth
from zork.collections.schema import RelationField

app = Zork(database="app.db")

posts = Collection("posts", fields=[
    TextField("title", required=True),
    TextField("body"),
    IntField("views", default=0),
    BoolField("is_published", default=False),
    RelationField("author", collection="users"),
])

auth = Auth(
    allow_registration=True,
    access_token_expiry=3600,
    refresh_token_expiry=604800,
    blocklist_backend="database",
    token_delivery="bearer",
)

app.register(posts, auth=["read:public", "write:authenticated"])
app.use_auth(auth)

if __name__ == "__main__":
    app.serve()
```

```bash
zork serve main.py
```

## Philosophy

Zork exists for developers who want to ship APIs fast without sacrificing production-readiness.

- **Schema-first** — Define your data model in Python. Zork handles the rest.
- **Zero boilerplate** — One file gets you CRUD, auth, pagination, filtering, and OpenAPI docs.
- **Production-ready by default** — JWT with rotation, CSRF protection, rate limiting, structured logging, and schema migrations.
- **Flexible** — Start simple. Scale to PostgreSQL, Redis, S3, and WebSockets as your app grows.

## Features

| Category | Feature |
|----------|---------|
| **API** | Auto-generated CRUD REST API from Python schemas |
| | OpenAPI 3.1 + Swagger UI auto-generated |
| | URL-based API versioning (`/api/v1`, `/api/v2`) |
| | Enhanced pagination with total count, next/prev, HAL-style links |
| | Filtering and sorting on any field |
| | Response transformation — include, exclude, alias fields |
| **Auth** | JWT authentication with RS256/HS256 |
| | Role-based access control (RBAC) |
| | HTTP-only cookie delivery with CSRF protection |
| | Refresh token rotation with automatic blocklist |
| | Configurable token expiry and delivery method |
| | Extend the user model with custom fields |
| **Database** | Multi-database: SQLite, PostgreSQL, MySQL |
| | Schema auto-sync for development |
| | Migration engine with diff, sync, rollback |
| | Connection pooling for PostgreSQL and MySQL |
| **Realtime** | WebSocket and Server-Sent Events (SSE) |
| | Redis pub/sub broker for horizontal scaling |
| | Publish events from lifecycle hooks |
| **Storage** | Local filesystem storage (zero config) |
| | S3-compatible storage (AWS S3, Cloudflare R2, MinIO, Backblaze B2, DigitalOcean Spaces, Wasabi, GCS) |
| | Presigned URLs for secure direct uploads |
| | File type and size validation |
| **Performance** | In-memory or Redis-backed caching |
| | Tag-based cache invalidation |
| | Per-route rate limiting |
| **Dev Tools** | Lifecycle hooks (`before_create`, `after_update`, etc.) |
| | Structured JSON logging with request tracing |
| | Configurable CORS (secure defaults) |
| | Static file serving with SPA fallback |
| | `zork deploy` — one-command deployment configs |
| | `zork doctor` — connectivity health check |
| | `zork routes` — list all registered routes |
| | `zork info` — app metadata and configuration |

## Authentication

Zork supports two token delivery methods. Choose based on your client:

### Cookie Delivery (Recommended for Web Apps)

Uses HTTP-only cookies with CSRF protection. Tokens are stored automatically by the browser and are resistant to XSS attacks. Revocation is instant when using Redis.

```python
auth = Auth(
    token_delivery="cookie",
    blocklist_backend="redis",
    cookie_secure=True,
    cookie_samesite="lax",
    csrf_enable=True,
    max_refresh_tokens=5,
    allow_registration=True,
)
```

### Bearer Delivery (Recommended for Mobile, SPAs, APIs)

Tokens are returned in JSON responses. The client stores and sends them manually via the `Authorization` header.

```python
auth = Auth(
    token_delivery="bearer",
    blocklist_backend="redis",
    allow_registration=True,
)
```

### Access Control

Apply rules when registering a collection:

```python
app.register(posts, auth=[
    "read:public",      # Anyone can read
    "write:authenticated",  # Must be logged in to create
])
```

Available rules: `read:public`, `read:authenticated`, `read:owner`, `read:admin`, `write:public`, `write:authenticated`, `write:owner`, `write:admin`.

### Auth Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Create a new user account |
| POST | `/api/auth/login` | Log in and receive tokens |
| POST | `/api/auth/logout` | Log out and revoke tokens |
| POST | `/api/auth/refresh` | Refresh access token |
| POST | `/api/auth/forgot-password` | Request password reset email |
| POST | `/api/auth/reset-password` | Reset password with token |
| GET | `/api/auth/me` | Get current authenticated user |
| GET | `/api/auth/verify/{token}` | Verify email address |

## Field Types

| Field | Description | Extra Options |
|-------|-------------|---------------|
| `TextField` | UTF-8 string | `min_length`, `max_length` |
| `IntField` | 64-bit integer | `min_value`, `max_value` |
| `FloatField` | Double-precision float | `min_value`, `max_value` |
| `BoolField` | Boolean (`True`/`False`) | — |
| `DateTimeField` | ISO 8601 datetime | `auto_now` (auto-update on change) |
| `URLField` | Validated URL string | — |
| `JSONField` | Arbitrary JSON data | — |
| `FileField` | File upload | `max_size`, `allowed_types`, `multiple`, `public` |
| `RelationField` | Reference to another collection | `collection` |

All fields share these common options: `required`, `default`, `unique`, `indexed`, `hidden`, `read_only`, `alias`.

## CLI Reference

```bash
# Development
zork serve main.py                  # Start the server
zork serve main.py --reload         # Auto-reload on file changes
zork serve main.py --port 9000       # Custom port
zork init myproject                  # Scaffold a new project

# Database
zork migrate run                     # Apply pending migrations
zork migrate status                  # Show migration status
zork migrate rollback               # Roll back last migration
zork migrate create add_tags        # Create a migration
zork migrate sync --app main.py     # Generate migrations from schema diff
zork schema diff --app main.py      # Show schema differences

# Deployment
zork deploy --platform docker        # Generate Docker configuration
zork deploy --platform railway      # Generate Railway configuration
zork deploy --platform render       # Generate Render configuration
zork deploy --platform fly         # Generate Fly.io configuration

# Utilities
zork doctor                          # Check connectivity to services
zork routes --app main.py           # List all registered routes
zork info --app main.py             # Show app metadata
zork promote user@example.com --role admin  # Promote a user
zork generate-secret                # Generate a secure JWT secret
```

## Environment Variables

Set these for production deployments:

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `ZORK_SECRET` | Yes (auth) | JWT signing secret | Auto-generated |
| `ZORK_DATABASE_URL` | No | Database connection URL | `app.db` |
| `ZORK_REDIS_URL` | No | Redis connection URL | — |
| `ZORK_AUTH_DELIVERY` | No | Token delivery (`bearer` or `cookie`) | `bearer` |
| `ZORK_ACCESS_TOKEN_EXPIRY` | No | Access token lifetime (seconds) | `3600` |
| `ZORK_REFRESH_TOKEN_EXPIRY` | No | Refresh token lifetime (seconds) | `604800` |
| `ZORK_COOKIE_SECURE` | No | Require HTTPS for cookies | `true` |
| `ZORK_COOKIE_SAMESITE` | No | SameSite policy | `lax` |
| `ZORK_CSRF_ENABLE` | No | Enable CSRF protection | `true` |
| `ZORK_BLOCKLIST_BACKEND` | No | Blocklist backend (`database` or `redis`) | `database` |
| `ZORK_RATE_LIMIT_ANON` | No | Anonymous rate limit | `100/60` |
| `ZORK_RATE_LIMIT_USER` | No | Authenticated rate limit | `1000/60` |
| `ZORK_CACHE_TTL` | No | Cache default TTL (seconds) | `300` |
| `ZORK_LOG_LEVEL` | No | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `ZORK_LOG_FORMAT` | No | Log format (`console` or `json`) | `console` |

For the full list of environment variables, see the [Environment Variables Reference](/deployment/environment-variables) in the documentation.

## Documentation

The full documentation is in the [`docs/`](docs/) directory. We recommend viewing it with a Markdown viewer (VS Code, GitHub, JetBrains, etc.) for the best experience. A hosted documentation website is coming soon.

| Section | What You'll Find |
|---------|-----------------|
| **[Getting Started](/docs/getting-started/)** | Installation, quick start, project structure |
| **[Core Concepts](/docs/core-concepts/)** | The app, collections, field types, relations, lifecycle hooks, middleware, errors, logging, response models |
| **[Authentication](/docs/authentication/)** | Setup, user model, endpoints, security (JWT, blocklists, CSRF) |
| **[Database](/docs/database/)** | Overview, migrations, schema safety |
| **[File Storage](/docs/file-storage/)** | Setup, storage providers (local, S3, R2, MinIO, and more) |
| **[Email](/docs/email/)** | SMTP and provider presets (Gmail, SendGrid, SES, Mailgun, Mailtrap, Postmark, Resend) |
| **[Realtime](/docs/realtime/)** | WebSocket and SSE overview, Redis broker |
| **[Caching](/docs/caching/)** | Memory and Redis caching backends |
| **[Rate Limiting](/docs/rate-limiting/)** | Configuring per-route rate limits |
| **[API Reference](/docs/api/)** | Endpoints, filtering, pagination, OpenAPI |
| **[Deployment](/docs/deployment/)** | Docker, Railway, Render, Fly.io |
| **[Guides](/docs/guides/)** | Troubleshooting common issues |

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines before submitting PRs. The codebase includes 60+ tests. Run them with:

```bash
uv add ".[dev]"
uv run pytest
```

## License

[MIT](LICENSE)