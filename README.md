# Cinder

A lightweight, open-source backend framework for Python. Build production-ready REST APIs with built-in auth, dynamic collections, and pluggable multi-database support — no heavy frameworks required.

Define your data schema in Python, and Cinder auto-generates a full CRUD API with JWT authentication, role-based access control, filtering, pagination, and relation expansion.

## Table of Contents

- [Install](#install)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Field Types](#field-types)
- [Authentication](#authentication)
- [API Endpoints](#api-endpoints)
- [OpenAPI / Swagger](#openapi--swagger)
- [Filtering, Pagination & Sorting](#filtering-pagination--sorting)
- [Relations & Expand](#relations--expand)
- [Hooks & Lifecycle Events](#hooks--lifecycle-events)
- [File Storage](#file-storage)
- [Email](#email)
- [Database](#database)
- [Realtime](#realtime)
- [Caching](#caching)
- [Rate Limiting](#rate-limiting)
- [Redis](#redis)
- [Middleware](#middleware)
- [CLI](#cli)
- [Migrations](#migrations)
- [Configuration](#configuration)
- [Roadmap](#roadmap)
- [License](#license)

---

## Install

```bash
pip install cinder
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add cinder
```

**Optional extras:**

```bash
pip install cinder[s3]        # S3-compatible file storage (boto3) — AWS, R2, MinIO, etc.
pip install cinder[email]     # Email delivery (aiosmtplib)
pip install cinder[redis]     # Redis caching & sessions
pip install cinder[postgres]  # PostgreSQL support (asyncpg)
pip install cinder[mysql]     # MySQL support (aiomysql)
pip install cinder[all]       # All extras
```

---

## Quick Start

Create a file called `main.py`:

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

Run it:

```bash
cinder serve main.py
# Server running at http://localhost:8000
```

That's it. You now have:

- `POST /api/auth/register` — register users
- `POST /api/auth/login` — get a JWT token
- `GET /api/posts` — list posts (public)
- `POST /api/posts` — create a post (requires auth)
- `GET /api/posts/{id}` — get a single post
- `PATCH /api/posts/{id}` — update a post
- `DELETE /api/posts/{id}` — delete a post
- `GET /api/health` — health check
- `GET /openapi.json` — OpenAPI 3.1 schema
- `GET /docs` — Swagger UI (requires internet)

---

## Core Concepts

### Collections

A **Collection** defines a data schema that Cinder turns into a database table and a full REST API.

```python
from cinder import Collection, TextField, IntField, FloatField, BoolField

products = Collection("products", fields=[
    TextField("name", required=True, max_length=200),
    TextField("description"),
    FloatField("price", required=True, min_value=0),
    IntField("stock", default=0),
    BoolField("is_published", default=False),
])
```

Every collection automatically includes these system fields:
- `id` — UUID4 primary key (auto-generated)
- `created_at` — ISO 8601 timestamp (auto-set on create)
- `updated_at` — ISO 8601 timestamp (auto-set on create and update)

### Registering Collections

```python
app = Cinder(database="app.db")
app.register(products, auth=["read:public", "write:authenticated"])
```

The `auth` parameter defines access control rules using the format `"operation:level"`:

| Rule | Meaning |
|------|---------|
| `read:public` | Anyone can read (no auth required) |
| `read:authenticated` | Only logged-in users can read |
| `read:owner` | Users can only read their own records |
| `read:admin` | Only admins can read |
| `write:public` | Anyone can write (no auth required) |
| `write:authenticated` | Only logged-in users can write |
| `write:owner` | Users can only modify/delete their own records |
| `write:admin` | Only admins can write |

When using the `owner` rule, Cinder automatically adds a `created_by` column that tracks which user created each record.

### Schema Auto-Sync

On startup, Cinder compares your collection definitions to the database:

- **New collection** — creates the table
- **New field added** — adds the column via `ALTER TABLE`
- **Field removed from code** — logs a warning but **never drops** the column (data preservation)

This means you can safely add fields to your collections and restart — existing data is preserved.

---

## Field Types

| Type | SQLite Type | Parameters | Description |
|------|------------|------------|-------------|
| `TextField` | TEXT | `required`, `default`, `unique`, `min_length`, `max_length` | String values |
| `IntField` | INTEGER | `required`, `default`, `unique`, `min_value`, `max_value` | Integer values |
| `FloatField` | REAL | `required`, `default`, `unique`, `min_value`, `max_value` | Floating-point values |
| `BoolField` | INTEGER | `required`, `default`, `unique` | Boolean values (stored as 0/1) |
| `DateTimeField` | TEXT | `required`, `default`, `unique`, `auto_now` | ISO 8601 datetime strings |
| `URLField` | TEXT | `required`, `default`, `unique` | Validated URL strings |
| `JSONField` | TEXT | `required`, `default` | Arbitrary JSON data (stored as string) |
| `RelationField` | TEXT | `required`, `unique`, `collection` | Foreign key reference to another collection |
| `FileField` | TEXT | `max_size`, `allowed_types`, `multiple`, `public` | File upload — metadata stored in SQLite, bytes in storage backend |

### Common Parameters

All field types accept:
- `required` (bool) — field must be provided on create. Default: `False`
- `default` (any) — default value when field is not provided. Default: `None`
- `unique` (bool) — enforce uniqueness in the database. Default: `False`

### Examples

```python
from cinder import (
    TextField, IntField, FloatField, BoolField,
    DateTimeField, URLField, JSONField, RelationField,
)
from cinder.collections.schema import Collection

Collection("articles", fields=[
    # Text with length constraints
    TextField("title", required=True, min_length=1, max_length=200),
    TextField("slug", unique=True),

    # Numbers with range validation
    IntField("views", default=0, min_value=0),
    FloatField("rating", min_value=0.0, max_value=5.0),

    # Boolean
    BoolField("is_draft", default=True),

    # Auto-updating timestamp
    DateTimeField("published_at", auto_now=True),

    # Validated URL
    URLField("source_url"),

    # Arbitrary JSON
    JSONField("metadata", default={}),

    # Foreign key to another collection
    RelationField("author", collection="users"),
])
```

---

## Authentication

### Setup

```python
from cinder import Auth

auth = Auth(
    token_expiry=86400,         # Token lifetime in seconds (default: 24h)
    allow_registration=True,    # Allow public registration (default: True)
)

app.use_auth(auth)
```

### Extending the User Model

Add custom fields to the built-in `_users` table:

```python
from cinder import Auth, TextField, IntField

auth = Auth(
    extend_user=[
        TextField("display_name"),
        TextField("avatar_url"),
        IntField("age"),
    ],
)
```

Extended fields can be provided during registration:

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secure123", "display_name": "John"}'
```

### User Roles

Every user has a `role` field (default: `"user"`). Use the CLI to promote users:

```bash
cinder promote user@example.com --role admin
```

### Auth Endpoints

#### Register — `POST /api/auth/register`

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secure123", "username": "john"}'
```

Response (`201`):
```json
{
  "token": "eyJhbGciOi...",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "username": "john",
    "role": "user",
    "is_verified": 0,
    "is_active": 1,
    "created_at": "2026-04-07T12:00:00+00:00",
    "updated_at": "2026-04-07T12:00:00+00:00"
  }
}
```

#### Login — `POST /api/auth/login`

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secure123"}'
```

Response (`200`):
```json
{
  "token": "eyJhbGciOi...",
  "user": { ... }
}
```

#### Get Current User — `GET /api/auth/me`

```bash
curl http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer eyJhbGciOi..."
```

Response (`200`):
```json
{
  "id": "550e8400-...",
  "email": "user@example.com",
  "role": "user",
  ...
}
```

#### Logout — `POST /api/auth/logout`

Revokes the current token (added to blocklist).

```bash
curl -X POST http://localhost:8000/api/auth/logout \
  -H "Authorization: Bearer eyJhbGciOi..."
```

Response (`200`):
```json
{ "message": "Logged out" }
```

After logout, the token is permanently invalidated and cannot be reused.

#### Refresh Token — `POST /api/auth/refresh`

Issues a new token and revokes the old one.

```bash
curl -X POST http://localhost:8000/api/auth/refresh \
  -H "Authorization: Bearer eyJhbGciOi..."
```

Response (`200`):
```json
{ "token": "eyJhbGciOi..." }
```

#### Forgot Password — `POST /api/auth/forgot-password`

```bash
curl -X POST http://localhost:8000/api/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

Response (`200`):
```json
{ "message": "If the email exists, a reset link has been generated" }
```

When `app.email` is configured, a password-reset link is dispatched automatically. Without email configuration the reset token is logged to the console (development fallback).

#### Verify Email — `GET /api/auth/verify-email?token=<token>`

Verifies a user's email address using the token sent after registration.

```bash
curl http://localhost:8000/api/auth/verify-email?token=<verification-token>
```

Response (`200`):
```json
{ "message": "Email verified successfully" }
```

Returns `400` for an unknown, already-used, or expired token. Tokens expire after 24 hours. Sending a new verification email (future feature) automatically invalidates the previous token.

#### Reset Password — `POST /api/auth/reset-password`

```bash
curl -X POST http://localhost:8000/api/auth/reset-password \
  -H "Content-Type: application/json" \
  -d '{"token": "reset-token-from-console", "new_password": "newpass123"}'
```

Response (`200`):
```json
{ "message": "Password updated" }
```

---

## API Endpoints

For every registered collection, Cinder generates these endpoints:

### List Records — `GET /api/{collection}`

```bash
curl http://localhost:8000/api/products
```

Response (`200`):
```json
{
  "items": [
    {
      "id": "...",
      "name": "Phone",
      "price": 999.99,
      "stock": 50,
      "is_published": true,
      "created_at": "2026-04-07T12:00:00",
      "updated_at": "2026-04-07T12:00:00"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### Get Record — `GET /api/{collection}/{id}`

```bash
curl http://localhost:8000/api/products/550e8400-e29b-41d4-a716-446655440000
```

Response (`200`):
```json
{
  "id": "550e8400-...",
  "name": "Phone",
  "price": 999.99,
  "stock": 50,
  "is_published": true,
  "created_at": "...",
  "updated_at": "..."
}
```

Returns `404` if the record does not exist.

### Create Record — `POST /api/{collection}`

```bash
curl -X POST http://localhost:8000/api/products \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOi..." \
  -d '{"name": "Phone", "price": 999.99, "stock": 50, "is_published": true}'
```

Response (`201`):
```json
{
  "id": "newly-generated-uuid",
  "name": "Phone",
  "price": 999.99,
  "stock": 50,
  "is_published": true,
  "created_at": "...",
  "updated_at": "..."
}
```

Returns `400` if validation fails (missing required fields, type mismatch, constraint violations).

### Update Record — `PATCH /api/{collection}/{id}`

Uses PATCH semantics — only send the fields you want to update.

```bash
curl -X PATCH http://localhost:8000/api/products/550e8400-... \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOi..." \
  -d '{"stock": 49}'
```

Response (`200`):
```json
{
  "id": "550e8400-...",
  "name": "Phone",
  "price": 999.99,
  "stock": 49,
  "is_published": true,
  "created_at": "...",
  "updated_at": "2026-04-07T13:00:00"
}
```

### Delete Record — `DELETE /api/{collection}/{id}`

```bash
curl -X DELETE http://localhost:8000/api/products/550e8400-... \
  -H "Authorization: Bearer eyJhbGciOi..."
```

Response (`200`):
```json
{ "message": "Record deleted" }
```

### Health Check — `GET /api/health`

```bash
curl http://localhost:8000/api/health
```

Response (`200`):
```json
{ "status": "ok" }
```

---

## OpenAPI / Swagger

Cinder auto-generates a full OpenAPI 3.1 schema and provides an interactive Swagger UI for exploring and testing your API.

**Note:** Swagger UI requires internet to load assets from CDN.

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /openapi.json` | OpenAPI 3.1 schema |
| `GET /docs` | Interactive Swagger UI |

### Customization

Customize the API title and version when initializing Cinder:

```python
app = Cinder(
    title="My API",
    version="1.0.0",
    database="app.db"
)
```

### What's Documented

The schema automatically includes:

- **Auth endpoints** — register, login, logout, refresh, password reset, email verification
- **Collection CRUD** — list, get, create, update, delete
- **Query parameters** — `limit`, `offset`, `order_by`, `expand`
- **Auth requirements** — Bearer token security on protected endpoints
- **Field constraints** — min/max values, required fields, field types

### Testing

```bash
curl http://localhost:8000/openapi.json | jq .
```

Or visit `http://localhost:8000/docs` in your browser for the interactive Swagger UI.

---

## Filtering, Pagination & Sorting

### Filtering

Filter records by passing field values as query parameters:

```bash
# Exact match
GET /api/products?is_published=true

# Multiple filters (AND)
GET /api/products?stock=50&is_published=true

# Filter by any field
GET /api/products?name=Phone
```

### Pagination

Control pagination with `limit` and `offset`:

```bash
# First page (10 items)
GET /api/products?limit=10&offset=0

# Second page
GET /api/products?limit=10&offset=10
```

Default: `limit=20`, `offset=0`. The response always includes `total` (total matching records), so you can calculate total pages.

### Sorting

Sort by any field using `order_by`:

```bash
# Sort by price
GET /api/products?order_by=price

# Sort by creation date
GET /api/products?order_by=created_at
```

Default sort: `created_at`.

### Combined Example

```bash
GET /api/products?is_published=true&order_by=price&limit=5&offset=0
```

---

## Relations & Expand

### Defining Relations

Use `RelationField` to create a foreign key reference to another collection:

```python
categories = Collection("categories", fields=[
    TextField("name", required=True),
])

products = Collection("products", fields=[
    TextField("name", required=True),
    FloatField("price", required=True),
    RelationField("category", collection="categories"),
])

app.register(categories, auth=["read:public", "write:authenticated"])
app.register(products, auth=["read:public", "write:authenticated"])
```

When creating a product, pass the related record's ID:

```bash
curl -X POST http://localhost:8000/api/products \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ..." \
  -d '{"name": "Phone", "price": 999.99, "category": "category-uuid-here"}'
```

### Expanding Relations

By default, relation fields return just the ID. Use `?expand=` to inline the full related record:

```bash
GET /api/products/product-uuid?expand=category
```

Response:
```json
{
  "id": "product-uuid",
  "name": "Phone",
  "price": 999.99,
  "category": "category-uuid",
  "expand": {
    "category": {
      "id": "category-uuid",
      "name": "Electronics",
      "created_at": "...",
      "updated_at": "..."
    }
  }
}
```

Expand multiple relations with comma-separated field names:

```bash
GET /api/products/product-uuid?expand=category,brand
```

Expand also works on list endpoints:

```bash
GET /api/products?expand=category
```

---

## Hooks & Lifecycle Events

Cinder ships with a flexible hook system that lets you run custom logic around every CRUD operation, auth event, and app-level lifecycle moment — plus any custom event you invent yourself. Built-in events and your own events live in the same registry and run through the same async runner. Any string is a valid event name.

### Registering Hooks

Define your handler function, then pass it into `.on()`. Three surfaces — pick whichever fits the scope:

```python
async def add_slug(data, ctx):
    data["slug"] = data["title"].lower().replace(" ", "-")
    return data

async def send_welcome_email(user, ctx):
    await mailer.send(to=user["email"], subject="Welcome!")

async def alert_security_team(data, ctx):
    await slack.post(f"Fraud detected: {data}")

# Collection-scoped
posts.on("before_create", add_slug)

# Auth-scoped — namespaced internally as "auth:after_register"
auth.on("after_register", send_welcome_email)
auth.on("email_verified", unlock_features)

# App-level / cross-cutting — any event string, built-in or custom
app.on("fraud:detected", alert_security_team)
```

This is the canonical form and matches the spec one-to-one. A decorator form is also available as sugar if you prefer to define and register in one step:

```python
@posts.on("before_create")
async def add_slug(data, ctx):
    data["slug"] = data["title"].lower().replace(" ", "-")
    return data
```

Both call the exact same code path — use whichever reads better for your project.

### Handler Signature

Every handler receives `(payload, ctx)`:

- `payload` — the data being operated on. Type depends on the event (see table below).
- `ctx` — a `CinderContext` with `user`, `request_id`, `collection`, `operation`, `request`, and `extra`.

Handlers may be **sync or async** — Cinder awaits both transparently.

**Mutation rule:** `before_*` handlers mutate the payload by **returning it**. Returning `None` leaves the payload unchanged. `after_*` handlers can return `None` — their return value is ignored by the runner.

### Built-in Events

Fired automatically around every CRUD operation:

| Event | Payload | Mutable? |
|-------|---------|----------|
| `{collection}:before_create` | incoming data dict | yes (return mutated dict) |
| `{collection}:after_create` | saved record dict | no |
| `{collection}:before_read` | record id (string) | yes |
| `{collection}:after_read` | fetched record dict | yes |
| `{collection}:before_list` | `{filters, order_by, limit, offset}` dict | yes |
| `{collection}:after_list` | list of records | yes |
| `{collection}:before_update` | incoming update dict | yes |
| `{collection}:after_update` | `(new_record, previous_record)` tuple | no |
| `{collection}:before_delete` | record about to be deleted | no (see cancel-delete) |
| `{collection}:after_delete` | deleted record | no |

Auth events:

```
auth:before_register    auth:after_register
auth:before_login       auth:after_login
auth:before_logout      auth:after_logout
auth:before_password_reset    auth:after_password_reset
auth:after_verify_email
```

App-level events:

```
app:startup     app:shutdown     app:error
```

### Example: Slugify on Create

```python
from cinder import Cinder, Collection, TextField

app = Cinder(database="app.db")
posts = Collection("posts", fields=[
    TextField("title", required=True),
    TextField("slug"),
])
app.register(posts, auth=["read:public", "write:authenticated"])

async def add_slug(data, ctx):
    data["slug"] = data["title"].lower().replace(" ", "-")
    return data

posts.on("before_create", add_slug)
```

### Example: Aborting an Operation

Raise `CinderError` from any hook to stop the chain and return an error response:

```python
from cinder.errors import CinderError

async def protect_pinned(record, ctx):
    if record.get("pinned"):
        raise CinderError(403, "Pinned posts cannot be deleted")

posts.on("before_delete", protect_pinned)
```

### Example: Soft Delete

Use the `cancel_delete()` sentinel to skip the actual DB delete without returning an error — handy for soft-delete patterns:

```python
async def soft_delete(record, ctx):
    await db.execute(
        "UPDATE messages SET is_deleted = 1 WHERE id = ?", (record["id"],)
    )
    raise CinderError.cancel_delete()

messages.on("before_delete", soft_delete)
```

`DELETE /api/messages/{id}` still returns `200 OK` and the record stays in the database with `is_deleted = 1`.

### Custom Events

Any string is a valid event name. You don't register event names upfront — just fire them.

```python
# Handlers for the custom event — same API as built-ins
async def trigger_shipping(record, ctx):
    await create_shipment(record)

async def send_receipt(record, ctx):
    await email_receipt(record)

orders.on("payment_confirmed", trigger_shipping)
orders.on("payment_confirmed", send_receipt)

# Fire the custom event from inside a built-in hook
async def on_payment_updated(payload, ctx):
    record, prev = payload
    if record["status"] == "paid" and prev["status"] == "pending":
        await orders.fire("payment_confirmed", record, ctx)

orders.on("after_update", on_payment_updated)
```

Cross-collection events live on the app-level bus:

```python
async def suspend_account(data, ctx): ...
async def notify_security(data, ctx): ...

app.on("fraud:detected", suspend_account)
app.on("fraud:detected", notify_security)

# Fire from anywhere
await app.hooks.fire("fraud:detected", {"user_id": "..."}, ctx)
```

Firing an event with zero registered handlers is a no-op — no error raised.

### App Lifecycle

```python
async def seed(_, ctx):
    # Called once when the server starts (inside Starlette's lifespan)
    await seed_database()

async def cleanup(_, ctx):
    await flush_queues()

async def log_error(exc, ctx):
    # Fired on any unhandled 500. Never masks the original response.
    await sentry.capture(exc, request_id=ctx.request_id)

app.on("app:startup", seed)
app.on("app:shutdown", cleanup)
app.on("app:error", log_error)
```

### Rules of Thumb

- Handlers execute in **registration order**, always.
- `before_*` hooks mutate by **returning** the payload; `None` means "unchanged".
- `after_*` hooks are fire-and-forget — return value ignored.
- Raising `CinderError` stops the chain and returns an error response to the client.
- `CinderError.cancel_delete()` stops the chain **without** an error — used for soft deletes.
- There is **one shared registry** per app, namespaced by event string. Collection / auth / app-level `on()` calls all land in the same place, so you can observe any event from any surface.
- Hook loop prevention is your responsibility — use guard clauses (`if record["already_processed"]: return`).

---

## File Storage

Cinder auto-generates upload, download, and delete endpoints for any collection field defined as `FileField`. File bytes are stored in a pluggable backend — local disk by default, or any S3-compatible object store in production. Switching backends requires changing one line.

Install the S3 extra to use cloud providers:

```bash
pip install cinder[s3]
# or
uv add cinder[s3]
```

### Defining a FileField

```python
from cinder import Cinder, Collection, TextField
from cinder.collections.schema import FileField
from cinder.storage import LocalFileBackend

posts = Collection("posts", fields=[
    TextField("title", required=True),
    # Single public image — anyone can download, auth required to upload
    FileField("cover", max_size=5_000_000, allowed_types=["image/*"], public=True),
    # Multiple private attachments — auth required to upload and download
    FileField("attachments", multiple=True, allowed_types=["application/pdf"]),
])

app = Cinder("app.db")
app.register(posts, auth=["read:public", "write:authenticated"])
app.configure_storage(LocalFileBackend("./uploads"))
```

### FileField Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_size` | `int` | `10_000_000` | Maximum file size in bytes (10 MB default) |
| `allowed_types` | `list[str]` | `["*/*"]` | Accepted MIME type patterns. Supports wildcards: `"image/*"`, `"*/*"` |
| `multiple` | `bool` | `False` | Allow multiple files per field (stored as a list) |
| `public` | `bool` | `False` | If `True`, the download route skips authentication. Use for avatars, cover images, etc. |

### Auto-Generated File Endpoints

For every `FileField`, Cinder generates three endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/{collection}/{id}/files/{field}` | Upload a file (multipart/form-data) |
| `GET` | `/api/{collection}/{id}/files/{field}` | Download or redirect to file |
| `DELETE` | `/api/{collection}/{id}/files/{field}` | Delete a file |

#### Upload — `POST /api/{collection}/{id}/files/{field}`

Send a `multipart/form-data` request with a `file` field:

```bash
curl -X POST http://localhost:8000/api/posts/post-uuid/files/cover \
  -H "Authorization: Bearer eyJhbGciOi..." \
  -F "file=@/path/to/photo.jpg"
```

Response (`201`) — the updated record with file metadata:
```json
{
  "id": "post-uuid",
  "title": "My Post",
  "cover": {
    "key": "posts/post-uuid/cover/a3f9b2c1_photo.jpg",
    "name": "photo.jpg",
    "size": 204800,
    "mime": "image/jpeg"
  }
}
```

For `multiple=True` fields, each upload appends to the list. Use `DELETE` with `?index=N` to remove individual files.

#### Download — `GET /api/{collection}/{id}/files/{field}`

```bash
# Single file
curl http://localhost:8000/api/posts/post-uuid/files/cover

# Multiple file — specify index
curl http://localhost:8000/api/posts/post-uuid/files/attachments?index=0 \
  -H "Authorization: Bearer eyJhbGciOi..."
```

- For remote backends (S3, R2, MinIO, etc.) — returns a `302` redirect to a time-limited **signed URL** (default: 15 minutes)
- For `LocalFileBackend` — proxies the bytes directly through the Cinder server
- For `FileField(public=True)` fields — no authentication required

#### Delete — `DELETE /api/{collection}/{id}/files/{field}`

```bash
# Delete the single file
curl -X DELETE http://localhost:8000/api/posts/post-uuid/files/cover \
  -H "Authorization: Bearer eyJhbGciOi..."

# Delete one file from a multiple field
curl -X DELETE "http://localhost:8000/api/posts/post-uuid/files/attachments?index=0" \
  -H "Authorization: Bearer eyJhbGciOi..."

# Delete all files in a multiple field
curl -X DELETE "http://localhost:8000/api/posts/post-uuid/files/attachments?all=true" \
  -H "Authorization: Bearer eyJhbGciOi..."
```

Deleting a record automatically removes all associated files from the storage backend (orphan cleanup via `after_delete` hooks).

### Storage Backends

#### LocalFileBackend

Zero configuration. Files are stored on disk under `base_path`. Best for development and single-server deployments.

```python
from cinder.storage import LocalFileBackend

app.configure_storage(LocalFileBackend("./uploads"))
```

Files are always served by proxying bytes through the Cinder server.

#### S3CompatibleBackend

Supports any S3-compatible object store via boto3. Uses presigned URLs for downloads — files are served directly from the provider, not through your server.

```python
from cinder.storage import S3CompatibleBackend

# AWS S3
app.configure_storage(S3CompatibleBackend.aws(
    bucket="my-bucket",
    access_key="AKIAIOSFODNN7EXAMPLE",
    secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    region="us-east-1",
))

# Cloudflare R2
app.configure_storage(S3CompatibleBackend.r2(
    account_id="your-cloudflare-account-id",
    bucket="my-bucket",
    access_key="your-r2-access-key",
    secret_key="your-r2-secret-key",
))

# MinIO
app.configure_storage(S3CompatibleBackend.minio(
    endpoint="http://localhost:9000",
    bucket="my-bucket",
    access_key="minioadmin",
    secret_key="minioadmin",
))

# Backblaze B2
app.configure_storage(S3CompatibleBackend.backblaze(
    endpoint="https://s3.us-west-001.backblazeb2.com",
    bucket="my-bucket",
    key_id="your-key-id",
    app_key="your-app-key",
))

# DigitalOcean Spaces
app.configure_storage(S3CompatibleBackend.digitalocean(
    region="nyc3",
    space="my-space",
    access_key="your-access-key",
    secret_key="your-secret-key",
))

# Wasabi
app.configure_storage(S3CompatibleBackend.wasabi(
    region="us-east-1",
    bucket="my-bucket",
    access_key="your-access-key",
    secret_key="your-secret-key",
))

# Google Cloud Storage (S3 interop — requires HMAC credentials)
app.configure_storage(S3CompatibleBackend.gcs(
    bucket="my-bucket",
    access_key="your-hmac-access-key",
    secret_key="your-hmac-secret",
))
```

All providers use the same underlying class — only the `endpoint_url` and `region_name` differ. Custom endpoint? Use the constructor directly:

```python
app.configure_storage(S3CompatibleBackend(
    bucket="my-bucket",
    access_key="key",
    secret_key="secret",
    endpoint_url="https://my-custom-provider.example.com",
    region_name="us-east-1",
    key_prefix="myapp",           # optional subfolder prefix
    signed_url_expires=1800,      # presigned URL lifetime in seconds (default 900)
))
```

#### Custom Backend

Subclass `FileStorageBackend` to integrate any storage system:

```python
from cinder.storage import FileStorageBackend

class MyStorageBackend(FileStorageBackend):
    async def put(self, key: str, data: bytes, content_type: str) -> None:
        # Store the file
        ...

    async def get(self, key: str) -> tuple[bytes, str]:
        # Return (data, content_type). Raise FileNotFoundError if missing.
        ...

    async def delete(self, key: str) -> None:
        # Delete the file. No-op if it doesn't exist.
        ...

    async def signed_url(self, key: str, expires_in: int = 900) -> str | None:
        # Return a presigned URL, or None to fall back to proxy mode.
        ...

    async def url(self, key: str) -> str | None:
        # Return a permanent public URL for public=True fields, or None.
        ...

app.configure_storage(MyStorageBackend())
```

### Security

Cinder enforces several protections on every file upload:

- **MIME type validation** — checks both the `Content-Type` header and the file's magic bytes (first 512 bytes). A file claiming to be `image/jpeg` but containing a PDF binary is rejected with `422`.
- **Size enforcement** — streaming read with a byte counter. The connection is aborted mid-stream before the full file is buffered if `max_size` is exceeded (`413`).
- **Path traversal prevention** — storage keys are always `{collection}/{id}/{field}/{uuid}_{sanitized_name}`. The user-supplied filename is sanitized (alphanumeric, `-`, `_`, `.` only) and prefixed with a UUID. User input never controls the storage path directly.
- **Auth gating** — upload and delete always require write permission. Download requires read permission unless `FileField(public=True)` is set explicitly.
- **Signed URL expiry** — presigned download URLs expire after 15 minutes by default (configurable via `signed_url_expires`). The URL is generated fresh per request and never stored.

---

## Email

Cinder has a built-in email delivery layer that powers password-reset links and email verification out of the box. It is completely **opt-in** — apps without email configuration continue to work exactly as before (reset tokens are logged to the console instead).

Install the email extra to enable SMTP delivery:

```bash
pip install cinder[email]
# or
uv add cinder[email]
```

### Zero-Config (Console Fallback)

No configuration is needed in development. Cinder falls back to `ConsoleEmailBackend` automatically when no backend is configured — all outbound emails are printed to the server log so you can inspect links and content.

```python
app = Cinder("app.db")
app.use_auth(Auth())   # email verification + password-reset emails → console log
```

### Connecting an SMTP Provider

Use `app.email.use(backend)` to plug in a real delivery backend, and `app.email.configure(...)` to set the sender address, app name, and base URL used in generated links.

```python
from cinder.email import SMTPBackend

app.email.use(SMTPBackend.sendgrid(api_key=os.getenv("SENDGRID_API_KEY")))
app.email.configure(
    from_address="no-reply@myapp.com",
    app_name="MyApp",
    base_url="https://myapp.com",
)
```

All emails are dispatched via `asyncio.create_task` — they never block the HTTP response. Failures are logged and swallowed so a broken SMTP connection never causes a `500` for the user.

### Provider Presets

| Preset | Host | Port | TLS Mode |
|--------|------|------|----------|
| `SMTPBackend.gmail(username, app_password)` | smtp.gmail.com | 587 | STARTTLS |
| `SMTPBackend.sendgrid(api_key)` | smtp.sendgrid.net | 587 | STARTTLS |
| `SMTPBackend.ses(region, key_id, secret)` | email-smtp.{region}.amazonaws.com | 587 | STARTTLS |
| `SMTPBackend.mailgun(username, password, eu=False)` | smtp.mailgun.org | 587 | STARTTLS |
| `SMTPBackend.mailtrap(api_token)` | live.smtp.mailtrap.io | 587 | STARTTLS |
| `SMTPBackend.postmark(api_token)` | smtp.postmarkapp.com | 587 | STARTTLS |
| `SMTPBackend.resend(api_key)` | smtp.resend.com | 465 | Implicit TLS |

```python
# Gmail (requires an App Password — not your account password)
app.email.use(SMTPBackend.gmail(
    username="me@gmail.com",
    app_password="xxxx xxxx xxxx xxxx",
))

# Amazon SES (use SMTP-specific credentials, not IAM keys)
app.email.use(SMTPBackend.ses(
    region="us-east-1",
    key_id=os.getenv("SES_SMTP_USER"),
    secret=os.getenv("SES_SMTP_PASSWORD"),
))

# Mailgun
app.email.use(SMTPBackend.mailgun(
    username="postmaster@mg.myapp.com",
    password=os.getenv("MAILGUN_SMTP_PASSWORD"),
))

# Resend (uses port 465 implicit TLS, not STARTTLS)
app.email.use(SMTPBackend.resend(api_key=os.getenv("RESEND_API_KEY")))

# Any custom SMTP server
from cinder.email import SMTPBackend
app.email.use(SMTPBackend(
    hostname="smtp.myhost.com",
    port=587,
    username="user@myhost.com",
    password="smtp-password",
    start_tls=True,
))
```

### Retry Behaviour

`SMTPBackend` retries transient failures (server disconnects, connection errors, timeouts) with exponential back-off. Permanent failures (authentication errors, rejected recipients) raise immediately without retrying.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_retries` | `3` | Maximum send attempts |
| `retry_base_delay` | `1.0` | Initial retry delay in seconds (doubles each attempt) |
| `timeout` | `30` | Connection and command timeout in seconds |

### Sending Custom Emails

`app.email.send()` can be called from hooks or anywhere in your code to send any transactional email:

```python
from cinder.email import EmailMessage

@app.on("orders:after_create")
async def send_order_confirmation(order, ctx):
    await app.email.send(EmailMessage(
        to=order["customer_email"],
        subject=f"Order #{order['id']} confirmed",
        html_body=f"<p>Your order <b>#{order['id']}</b> is confirmed.</p>",
        text_body=f"Your order #{order['id']} is confirmed.",
    ))
```

The `from_address` is filled in automatically from `app.email.configure(from_address=...)` if not set on the message.

### Customising Email Templates

Cinder ships built-in inline-styled HTML templates for password-reset, email verification, and welcome emails. Override any of them with your own callable — use plain f-strings, Jinja2, Mako, or any other template engine:

```python
# Plain f-string override
def my_reset_template(ctx):
    url = ctx["reset_url"]
    return (
        "Reset your password",
        f"<h1>Reset link</h1><a href='{url}'>Click here</a>",
        f"Reset link: {url}",
    )

app.email.on_password_reset(my_reset_template)

# Jinja2 override (install jinja2 separately)
from jinja2 import Environment, FileSystemLoader

jinja = Environment(loader=FileSystemLoader("templates/email"))

def jinja_reset(ctx):
    html = jinja.get_template("reset.html").render(**ctx)
    text = jinja.get_template("reset.txt").render(**ctx)
    return "Reset your password", html, text

app.email.on_password_reset(jinja_reset)
```

| Override method | Context dict keys | Description |
|-----------------|-------------------|-------------|
| `app.email.on_password_reset(fn)` | `reset_url`, `app_name`, `expiry_minutes` | Password-reset email |
| `app.email.on_verification(fn)` | `verify_url`, `app_name` | Email-verification email sent on registration |
| `app.email.on_welcome(fn)` | `user_email`, `app_name` | Welcome email (opt-in, call from a hook) |

Each callable receives the context dict and must return `(subject: str, html_body: str, text_body: str)`.

### Custom Backend

Subclass `EmailBackend` to integrate any delivery system — HTTP API, queue, SES SDK, etc.:

```python
from cinder.email import EmailBackend, EmailMessage
import httpx

class PostmarkHTTPBackend(EmailBackend):
    def __init__(self, server_token: str):
        self._token = server_token

    async def send(self, message: EmailMessage) -> None:
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.postmarkapp.com/email",
                headers={"X-Postmark-Server-Token": self._token},
                json={
                    "From": message.from_address,
                    "To": message.to,
                    "Subject": message.subject,
                    "HtmlBody": message.html_body,
                    "TextBody": message.text_body,
                },
            )

app.email.use(PostmarkHTTPBackend(server_token=os.getenv("POSTMARK_TOKEN")))
```

### Email Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CINDER_EMAIL_FROM` | `noreply@localhost` | Default sender address used in all outbound emails |
| `CINDER_APP_NAME` | `Your App` | App name shown in email templates |
| `CINDER_BASE_URL` | `http://localhost:8000` | Base URL prepended to verification and reset links |

These can be set in your `.env` file instead of calling `app.email.configure(...)`:

```env
CINDER_EMAIL_FROM=no-reply@myapp.com
CINDER_APP_NAME=MyApp
CINDER_BASE_URL=https://myapp.com
```

---

## Database

Cinder ships with SQLite out of the box (zero configuration, no server required) and supports PostgreSQL and MySQL in production through a pluggable `DatabaseBackend` system. Switching databases is a single environment variable — no code changes required.

### SQLite (default)

```python
app = Cinder(database="app.db")        # bare path — SQLite
app = Cinder(database="sqlite:///app.db")  # explicit scheme, same thing
```

SQLite runs in WAL mode with foreign key enforcement enabled. It is the recommended choice for development, small projects, and single-server deployments. No extras needed.

### PostgreSQL

Requires the `postgres` extra (`asyncpg`):

```bash
pip install cinder[postgres]
# or
uv add cinder[postgres]
```

```python
app = Cinder(database="postgresql://user:pass@localhost/mydb")
```

Cinder creates a **connection pool** (`asyncpg.create_pool`) with:
- Configurable `min_size` / `max_size` (default: 1 / 10)
- `max_inactive_connection_lifetime=300` seconds — prevents stale connections on serverless platforms (NeonDB, Supabase)
- One automatic retry on transient connection errors

#### NeonDB / Supabase (serverless Postgres)

```bash
DATABASE_URL=postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
```

No code change — just set the environment variable. The `?sslmode=require` suffix is handled by asyncpg natively.

### MySQL

Requires the `mysql` extra (`aiomysql`):

```bash
pip install cinder[mysql]
# or
uv add cinder[mysql]
```

```python
app = Cinder(database="mysql://user:pass@localhost:3306/mydb")
# Dialect aliases also accepted:
# "mysql+aiomysql://..."
# "mysql+asyncmy://..."
```

Cinder uses `aiomysql.create_pool` with `DictCursor` and `autocommit=True`. `TEXT PRIMARY KEY` is automatically rewritten to `VARCHAR(36) PRIMARY KEY` inside `CREATE TABLE` DDL (MySQL requires a length prefix for text primary keys; Cinder always uses 36-character UUID strings).

### Switching Between Environments

The recommended pattern is to write the default path in code and override it with an environment variable in production — **no code changes ever needed**:

```python
# main.py — never touch this line again
app = Cinder(database="app.db")
```

```bash
# .env.development
DATABASE_URL=sqlite:///dev.db

# .env.production (set on Railway, Render, Heroku, etc.)
DATABASE_URL=postgresql://user:pass@host/db

# .env.test
DATABASE_URL=sqlite:///test.db
```

**Priority chain (highest → lowest):**

| Priority | Source | Example |
|----------|--------|---------|
| 1 (highest) | `CINDER_DATABASE_URL` env var | Cinder-specific override |
| 2 | `DATABASE_URL` env var | Standard PaaS convention |
| 3 | `database=` constructor arg | Programmatic default |
| 4 (lowest) | `"app.db"` | Zero-config SQLite |

`CINDER_DATABASE_URL` beats `DATABASE_URL` when both are set — useful if your hosting platform injects `DATABASE_URL` but you want Cinder to use a different database.

### Advanced Configuration — `configure_database()`

For full control over pool size, SSL, and connection timeouts, pass a pre-configured backend directly:

```python
from cinder.db.backends.postgresql import PostgreSQLBackend

app.configure_database(
    PostgreSQLBackend(
        url=os.environ["DATABASE_URL"],
        min_size=2,
        max_size=20,
        max_inactive_connection_lifetime=60,  # aggressive for serverless
        ssl="require",
    )
)
```

`configure_database()` takes precedence over all environment variables and the `database=` constructor argument.

### Pool Size Environment Variables

These apply to PostgreSQL and MySQL backends:

| Variable | Default | Description |
|----------|---------|-------------|
| `CINDER_DB_POOL_MIN` | `1` | Minimum pool connections |
| `CINDER_DB_POOL_MAX` | `10` | Maximum pool connections |
| `CINDER_DB_POOL_TIMEOUT` | `30` | Seconds to wait for a free connection |
| `CINDER_DB_CONNECT_TIMEOUT` | `10` | Seconds to open a new connection |

### Custom Backend

Subclass `DatabaseBackend` to integrate any database driver — Turso, libsql, DynamoDB, or anything else:

```python
from cinder.db.backends.base import DatabaseBackend, DatabaseIntegrityError

class MyTursoBackend(DatabaseBackend):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def execute(self, sql: str, params: tuple = ()) -> None:
        # Raise DatabaseIntegrityError on UNIQUE/constraint violations
        ...
    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None: ...
    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]: ...
    async def table_exists(self, name: str) -> bool: ...
    async def get_columns(self, name: str) -> list[dict]:
        # Each dict must have at least a 'name' key
        ...

app.configure_database(MyTursoBackend())
```

All callers write SQL using `?` as the placeholder. Your backend converts it internally to whatever style the driver expects.

### Error Handling

| Situation | Response |
|-----------|----------|
| Cannot connect to host | `503 Service Unavailable` |
| Pool exhausted (too many concurrent requests) | `503 Service Unavailable` |
| UNIQUE / NOT NULL constraint violated | `400 Bad Request` |
| Transient connection loss during a request | Retried once automatically, then `503` |

---

## Realtime

Cinder has built-in realtime support via **WebSockets** and **Server-Sent Events (SSE)**. Both transports are first-class — neither is a wrapper around the other. Choose based on your client's needs: WebSocket for bidirectional communication, SSE for simple one-way streaming to browsers.

Realtime is enabled automatically when you call `app.build()`. No extra install, no separate server.

### Endpoints

| Endpoint | Transport | Description |
|----------|-----------|-------------|
| `GET /api/realtime/ws` | WebSocket | Persistent bidirectional connection |
| `GET /api/realtime/sse` | Server-Sent Events | HTTP streaming, browser-native |

### Channels

Everything in Cinder's realtime system is organized around **channels** — named event streams. There are two kinds:

| Channel format | Example | Description |
|----------------|---------|-------------|
| `collection:{name}` | `collection:posts` | Auto-emitted CRUD events for a registered collection |
| Any custom string | `chat:room-42`, `fraud:detected` | Your own events, published manually |

### Auto-Emit Bridge

When you register a collection, Cinder automatically wires up the hook system to publish events to the broker on every successful `create`, `update`, and `delete`. Your clients receive events in real time without any extra code.

**Envelope format** — every message has this shape:

```json
{
  "channel": "collection:posts",
  "event":   "create",
  "record":  { "id": "...", "title": "Hello", "created_at": "..." },
  "previous": null
}
```

| Field | Values | Description |
|-------|--------|-------------|
| `channel` | `collection:{name}` | The channel the event was published to |
| `event` | `create`, `update`, `delete` | The operation that triggered the event |
| `record` | object | The current state of the record |
| `previous` | object or `null` | Previous state of the record (only on `update`) |

---

### WebSocket

Connect to `/api/realtime/ws` and communicate via JSON messages.

#### Connecting

```js
const ws = new WebSocket("ws://localhost:8000/api/realtime/ws");
```

No token is required on connection. You can authenticate mid-session (see below).

#### Subscribing to a Channel

Send a `subscribe` action to start receiving events:

```json
{ "action": "subscribe", "channel": "collection:posts" }
```

Cinder acknowledges with:

```json
{ "type": "ack", "action": "subscribe", "channel": "collection:posts" }
```

Subscribe to multiple channels by sending multiple `subscribe` messages.

#### Receiving Events

Once subscribed, events arrive as JSON:

```json
{
  "channel": "collection:posts",
  "event":   "create",
  "record":  { "id": "abc", "title": "My Post", "created_at": "..." },
  "previous": null
}
```

#### Unsubscribing

```json
{ "action": "unsubscribe", "channel": "collection:posts" }
```

#### Authenticating Mid-Session

Send an `auth` message at any time to identify yourself:

```json
{ "action": "auth", "token": "eyJhbGciOi..." }
```

Cinder responds with:

```json
{ "type": "ack", "action": "auth" }
```

On success, your user identity is attached to the connection — subsequent events are filtered according to the collection's read rules (e.g. `owner`-scoped events will only show records you created).

If the token is invalid, the connection is closed with a `4401` close code.

#### Full Browser Example

```js
const ws = new WebSocket("ws://localhost:8000/api/realtime/ws");

ws.onopen = () => {
  // Optionally authenticate first
  ws.send(JSON.stringify({ action: "auth", token: localStorage.getItem("token") }));

  // Subscribe to a collection channel
  ws.send(JSON.stringify({ action: "subscribe", channel: "collection:posts" }));
};

ws.onmessage = ({ data }) => {
  const msg = JSON.parse(data);

  if (msg.type === "ack") {
    console.log("Acknowledged:", msg.action);
    return;
  }

  if (msg.channel === "collection:posts") {
    console.log(`Post ${msg.event}d:`, msg.record);
  }
};
```

---

### Server-Sent Events (SSE)

Connect to `/api/realtime/sse` with query parameters. The browser's native `EventSource` API works out of the box.

#### Subscribing

```
GET /api/realtime/sse?channel=collection:posts
GET /api/realtime/sse?channel=collection:posts&channel=collection:comments
GET /api/realtime/sse?token=eyJhbGciOi...&channel=collection:notes
```

| Query param | Required | Description |
|-------------|----------|-------------|
| `channel` | Yes | One or more channel names to subscribe to (repeatable) |
| `token` | Only for protected collections | JWT bearer token |

#### SSE Frame Format

Each event is sent as a standard SSE frame:

```
event: create
data: {"channel":"collection:posts","event":"create","record":{...},"previous":null}
id: <record-id>

```

A `: ping` comment is sent every 15 seconds to keep the connection alive through proxies and load balancers.

#### Full Browser Example

```js
const token = localStorage.getItem("token");
const url = `/api/realtime/sse?token=${token}&channel=collection:posts`;
const source = new EventSource(url);

source.addEventListener("create", (e) => {
  const data = JSON.parse(e.data);
  console.log("New post:", data.record);
});

source.addEventListener("update", (e) => {
  const data = JSON.parse(e.data);
  console.log("Post updated:", data.record);
});

source.addEventListener("delete", (e) => {
  const data = JSON.parse(e.data);
  console.log("Post deleted:", data.record.id);
});

source.onerror = () => {
  console.error("SSE connection lost, browser will retry automatically");
};
```

---

### Auth-Aware Filtering

Cinder automatically applies the collection's read rule as a realtime filter. Clients only receive events they are allowed to see.

| Read rule | WebSocket / SSE behaviour |
|-----------|--------------------------|
| `public` | All clients receive all events, no token required |
| `authenticated` | Only authenticated clients receive events |
| `admin` | Only clients whose token has `role: admin` receive events |
| `owner` | Each client only receives events for records they created (`created_by == user.id`) |

For **WebSocket**, authenticate mid-session with the `auth` action (see above). For **SSE**, pass `?token=` in the query string.

An invalid token returns `401` immediately. A missing token is allowed — the connection starts anonymous and events are filtered accordingly (public collections still stream).

---

### Custom Channels

You are not limited to collection channels. Publish to any string channel and subscribe to it from the client — same API.

**Server-side — publish from anywhere:**

```python
# From inside a hook
async def on_payment_updated(payload, ctx):
    record, prev = payload
    if record["status"] == "paid":
        await app.realtime.publish(
            "payments:completed",
            {"order_id": record["id"], "amount": record["total"]},
            event="payment_completed",
        )

orders.on("after_update", on_payment_updated)
```

**Client-side — subscribe via WebSocket:**

```js
ws.send(JSON.stringify({ action: "subscribe", channel: "payments:completed" }));
```

**Client-side — subscribe via SSE:**

```
GET /api/realtime/sse?channel=payments:completed
```

Custom channels carry no default auth filter — events are delivered to all subscribers. Apply your own filtering via the hook that publishes.

---

### Controlling Auto-Emit

By default, every `create`, `update`, and `delete` operation on a registered collection publishes to `collection:{name}`. You can turn this off globally or per-event:

```python
# Disable all auto-emit for this app
app.realtime.disable_auto_emit()

# Re-enable later
app.realtime.enable_auto_emit()
```

When auto-emit is disabled, you can still publish manually from hooks:

```python
async def manual_emit(record, ctx):
    await app.realtime.publish("collection:posts", record, event="create")

posts.on("after_create", manual_emit)
```

---

### Custom Envelope Builder

Override the default envelope format with your own builder:

```python
def my_envelope(collection_name, event, record, previous):
    return {
        "type":       "data",
        "collection": collection_name,
        "action":     event,
        "payload":    record,
        "diff":       previous,
        "ts":         time.time(),
    }

app.realtime.envelope_builder = my_envelope
```

The builder is called every time the bridge emits to the broker. Clients receive exactly what it returns.

---

### Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `CINDER_SSE_HEARTBEAT` | `15` | Seconds between SSE `ping` heartbeat comments |

```env
CINDER_SSE_HEARTBEAT=30
```

---

## Caching

Cinder ships with a **cache-aside** response cache for collection GET endpoints. It works out of the box with an in-memory backend (great for development) and scales to Redis for production multi-process deployments.

Install the Redis extra to use the Redis backend:

```bash
pip install cinder[redis]
```

### Zero-Config (In-Memory)

The in-memory backend requires no configuration and is enabled automatically when `CINDER_REDIS_URL` is set or you call `app.cache.enable()`.

```python
app = Cinder("app.db")
app.cache.enable()            # use in-memory backend (dev/test)
app.cache.configure(default_ttl=60)
```

### Redis Backend

```python
app = Cinder("app.db")
app.configure_redis(url="redis://localhost:6379/0")
# Cache, rate-limit, and realtime broker all use Redis automatically
```

Or set via environment variable:

```env
CINDER_REDIS_URL=redis://localhost:6379/0
```

### How It Works

- **Cache-aside**: GET requests to `/api/{collection}` and `/api/{collection}/{id}` are cached automatically on first hit.
- **X-Cache header**: Responses include `X-Cache: HIT` or `X-Cache: MISS`.
- **Per-user segmentation**: Cache keys include the user ID by default, so RBAC-filtered results never leak between users. Opt out per-collection with `per_user=False`.
- **Automatic invalidation**: Any `POST`, `PATCH`, or `DELETE` that triggers an `after_create/update/delete` hook automatically busts the relevant cache keys — no manual work needed.
- **Fail-open**: If the cache backend is down, requests pass through to the database without error.
- **Never cached**: 4xx/5xx responses, `Set-Cookie` responses, and `Cache-Control: no-store` responses.

### Programmatic Configuration

```python
from cinder import Cinder, RedisCacheBackend

app = Cinder("app.db")

# Use a custom backend
app.cache.use(RedisCacheBackend())

# Configure TTL and per-user segmentation
app.cache.configure(default_ttl=600, per_user=True)

# Opt specific paths out of caching
app.cache.exclude("/api/feed", "/api/search")

# Full example
app.cache \
    .use(RedisCacheBackend()) \
    .configure(default_ttl=300) \
    .exclude("/api/activity")
```

### Custom Backend

Subclass `CacheBackend` to use any storage system (Memcached, DynamoDB, etc.):

```python
from cinder import CacheBackend

class MyCacheBackend(CacheBackend):
    async def get(self, key: str) -> bytes | None: ...
    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None: ...
    async def delete(self, *keys: str) -> None: ...
    async def delete_pattern(self, pattern: str) -> None: ...
    async def sadd(self, set_key: str, *members: str) -> None: ...
    async def smembers(self, set_key: str) -> set[str]: ...
    async def sdelete(self, set_key: str) -> None: ...
    async def clear(self) -> None: ...
    async def close(self) -> None: ...

app.cache.use(MyCacheBackend())
```

### Cache Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CINDER_CACHE_ENABLED` | auto | `true`/`false`. Auto-enables when `CINDER_REDIS_URL` is set. |
| `CINDER_CACHE_TTL` | `300` | Default TTL in seconds |
| `CINDER_CACHE_PREFIX` | `cinder` | Redis key namespace prefix |

---

## Rate Limiting

Cinder includes a configurable rate limiter that protects every endpoint from abuse. It applies **before** the cache, so rejected requests never incur a cache lookup.

```python
app = Cinder("app.db")
app.configure_redis(url="redis://localhost:6379/0")
# Rate limiting is enabled automatically
```

On limit exceeded, Cinder returns:

```http
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1744147200
Retry-After: 42

{"status": 429, "error": "Rate limit exceeded"}
```

Every allowed response also carries the rate-limit headers so clients can track their budget.

### Default Limits

| Client type | Default limit |
|-------------|--------------|
| Anonymous (no token) | 100 requests / 60 seconds per IP |
| Authenticated | 1000 requests / 60 seconds per user |

Override via environment variables:

```env
CINDER_RATE_LIMIT_ANON=200/60
CINDER_RATE_LIMIT_USER=5000/60
```

### Per-Route Rules

Add tighter or looser limits for specific paths:

```python
from cinder import RateLimitRule

app.rate_limit.rule("/api/auth/login", limit=10, window=60, scope="ip")
app.rate_limit.rule("/api/posts", limit=50, window=60, scope="user")
```

| `scope` | Key used |
|---------|---------|
| `"ip"` | client IP address (default for anonymous) |
| `"user"` | authenticated user ID (default for authenticated) |
| `"both"` | user ID if authenticated, otherwise IP |

### Custom Backend

```python
from cinder import RateLimitBackend, RateLimitResult

class MyRateLimitBackend(RateLimitBackend):
    async def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        # Return RateLimitResult(allowed, remaining, reset_at)
        ...
    async def close(self) -> None: ...

app.rate_limit.use(MyRateLimitBackend())
```

### Rate-Limit Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CINDER_RATE_LIMIT_ENABLED` | `true` | Set to `false` to disable globally |
| `CINDER_RATE_LIMIT_ANON` | `100/60` | Anonymous limit in `requests/window_seconds` |
| `CINDER_RATE_LIMIT_USER` | `1000/60` | Authenticated limit in `requests/window_seconds` |

---

## Redis

`app.configure_redis(url=...)` is the single call that wires Redis into all three subsystems at once:

```python
app = Cinder("app.db")
app.configure_redis(url="redis://localhost:6379/0")
```

This is equivalent to setting `CINDER_REDIS_URL` in your `.env`.

| Subsystem | In-memory default | Redis (with `CINDER_REDIS_URL`) |
|-----------|------------------|---------------------------------|
| Cache | `MemoryCacheBackend` | `RedisCacheBackend` |
| Rate limiting | `MemoryRateLimitBackend` | `RedisRateLimitBackend` (atomic Lua token bucket) |
| Realtime broker | `RealtimeBroker` (in-process) | `RedisBroker` (pub/sub fan-out) |

### Multi-Process / Multi-Node Realtime

With the in-process broker, events only reach WebSocket/SSE clients connected to the **same process**. In production with multiple workers, enable the Redis broker:

```env
CINDER_REDIS_URL=redis://localhost:6379/0
CINDER_REALTIME_BROKER=redis
```

Or programmatically:

```python
app.configure_redis(url="redis://localhost:6379/0")
# CINDER_REALTIME_BROKER=redis activates RedisBroker automatically
# when CINDER_REDIS_URL is set
```

The `RedisBroker` satisfies the same `BrokerProtocol` as the in-process broker — no changes needed anywhere else in your code.

### Custom Broker

Implement `BrokerProtocol` to use any message bus (RabbitMQ, NATS, etc.):

```python
from cinder.realtime.broker import BrokerProtocol, Subscription

class MyBroker:
    async def subscribe(self, channels, *, user=None, filter=None) -> Subscription: ...
    async def unsubscribe(self, subscription: Subscription) -> None: ...
    async def publish(self, channel: str, envelope: dict) -> None: ...
    async def close(self) -> None: ...

    @property
    def subscription_count(self) -> int: ...
```

Pass it directly:

```python
app.realtime.use_broker(MyBroker())
```

---

## Middleware

Cinder includes built-in middleware layers applied to every request:

### Error Handling

All exceptions are caught and returned as structured JSON:

```json
{ "status": 400, "error": "Email and password are required" }
```

- `CinderError` exceptions return the specified status code and message
- Unhandled exceptions return `500` with `"Internal server error"` (details logged server-side)

### Request ID

Every response includes an `X-Request-ID` header with a unique UUID4 value. Useful for logging and debugging:

```
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
```

### CORS

Cross-Origin Resource Sharing is enabled by default with permissive settings:

- All origins allowed (`*`)
- All HTTP methods allowed
- All headers allowed
- Credentials supported

---

## CLI

### `cinder serve`

Start the application server.

```bash
cinder serve main.py
cinder serve main.py --host 127.0.0.1 --port 3000
cinder serve main.py --reload   # Auto-reload on file changes
```

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `0.0.0.0` | Host to bind to |
| `--port` | `8000` | Port to bind to |
| `--reload` | `False` | Enable auto-reload for development |

Cinder auto-discovers the `Cinder` instance in the given Python file.

### `cinder init`

Scaffold a new project with a starter `main.py`, `.env`, and `.gitignore`.

```bash
cinder init myproject
cd myproject
cinder serve main.py
```

Generated project structure:
```
myproject/
  main.py      # Starter app with posts collection + auth
  .env         # CINDER_SECRET placeholder
  .gitignore   # Ignores .db, .env, __pycache__, .venv
```

### `cinder promote`

Promote a user to a new role (e.g., admin).

```bash
cinder promote user@example.com --role admin
cinder promote user@example.com --role moderator --database myapp.db
```

| Option | Default | Description |
|--------|---------|-------------|
| `--role` | `admin` | Role to assign |
| `--database` | `app.db` | Path to the SQLite database |

### `cinder generate-secret`

Print a cryptographically secure random secret suitable for `CINDER_SECRET`.

```bash
cinder generate-secret
# e.g. a3f9d2c1b4e8f7a6d5c3b2e1f0a9d8c7b6e5f4a3d2c1b0e9f8a7d6c5b4e3f2a1
```

### `cinder doctor`

Check connectivity for your database and Redis (if configured). Exits with code 1 if any check fails — useful as a pre-deploy health gate.

```bash
cinder doctor --app main.py
cinder doctor --database postgresql://user:pass@host/db
```

| Option | Description |
|--------|-------------|
| `--app APP` | Load DB URL from the Cinder app |
| `--database URL` | Database URL to test directly |

If neither is provided, falls back to `CINDER_DATABASE_URL` → `DATABASE_URL` → `app.db`.

### `cinder routes`

Print every registered route in the application.

```bash
cinder routes --app main.py
```

Output:
```
METHOD   PATH                        NAME
GET      /api/posts                  list_posts
POST     /api/posts                  create_posts
GET      /api/posts/{id}             get_posts
...
GET      /docs                       swagger_ui
GET      /openapi.json               openapi
```

### `cinder info`

Print app metadata without starting the server.

```bash
cinder info --app main.py
```

Output:
```
Title:      My App
Version:    1.0.0
Python:     3.13.0
Cinder:     0.1.0
Database:   postgresql://***:***@host/mydb
Collections (3): posts, comments, users
Auth:       enabled
Storage:    S3CompatibleBackend
Broker:     RealtimeBroker
```

### `cinder migrate`

Apply pending migration files. See the [Migrations](#migrations) section for the full guide.

```bash
cinder migrate --app main.py           # apply pending
cinder migrate status --app main.py   # show history
cinder migrate rollback --app main.py # undo last
cinder migrate create add_index_posts --app main.py          # blank template
cinder migrate create add_missing_cols --app main.py --auto  # auto-generate from schema diff
```

---

## Migrations

Cinder's migration system provides explicit, version-tracked control over schema changes that go beyond the automatic column additions handled by [Schema Auto-Sync](#schema-auto-sync).

### When to Use Migrations vs Auto-Sync

| Change | Auto-Sync | Migration |
|--------|-----------|-----------|
| Add a new column | ✅ Handled on startup | Optional (for audit trail) |
| Create a new collection | ✅ Handled on startup | Optional |
| Add a database index | ❌ | ✅ Write a migration |
| Rename a column | ❌ | ✅ Write a migration |
| Transform existing data | ❌ | ✅ Write a migration |
| Drop a column | ❌ (preserved forever) | ✅ Uncomment generated SQL |

**Both run together** — auto-sync handles additive changes on every app startup; migration files handle the rest and are applied explicitly via `cinder migrate`.

### Migration Files

Migration files live in a `migrations/` directory. Each file is timestamped (`YYYYMMDD_HHMMSS_description.py`) and contains two async functions:

```python
# migrations/20260409_143022_add_index_posts_category.py
"""Add index on posts.category for faster category filtering."""

async def up(db):
    await db.execute("CREATE INDEX idx_posts_category ON posts (category)")

async def down(db):
    await db.execute("DROP INDEX IF EXISTS idx_posts_category")
```

The `db` argument is Cinder's `Database` object — call `db.execute()`, `db.fetch_all()`, `db.fetch_one()`, or any other method directly.

### Creating Migration Files

**Blank template** (you write the SQL):
```bash
cinder migrate create add_index_posts --app main.py
# Created migration: migrations/20260409_143022_add_index_posts.py
```

**Auto-generate from schema diff** (compares Collection definitions vs live DB):
```bash
cinder migrate create sync_schema --app main.py --auto
```

The `--auto` flag generates SQL for:
- New collections not yet in the database → `CREATE TABLE`
- New fields not yet in existing tables → `ALTER TABLE ADD COLUMN`
- Columns in the DB not in any collection → commented-out `DROP COLUMN` (destructive — requires manual uncomment)

### Applying Migrations

```bash
# Apply all pending
cinder migrate --app main.py

# Or explicitly
cinder migrate run --app main.py
```

Cinder applies each pending file in filename order and records it in `_schema_migrations`.

### Checking Status

```bash
cinder migrate status --app main.py
```

```
ID                                           STATUS    APPLIED AT
20260409_143022_add_index_posts_category     applied   2026-04-09T14:30:22+00:00
20260410_090000_add_audit_table              pending   -
```

Orphaned entries (applied but file deleted) appear with status `orphaned`.

### Rolling Back

```bash
cinder migrate rollback --app main.py
```

Rolls back the most recently applied migration (by `applied_at` timestamp) by calling its `down()` function and removing the tracking record.

### Custom Migrations Directory

All migrate commands accept `--dir` to override the default `migrations/` path:

```bash
cinder migrate --app main.py --dir db/migrations
cinder migrate create add_index --app main.py --dir db/migrations
```

### Migration Tracking

Applied migrations are recorded in `_schema_migrations`:

```sql
CREATE TABLE _schema_migrations (
    id         TEXT PRIMARY KEY,   -- migration filename without .py
    applied_at TEXT NOT NULL       -- UTC ISO 8601 timestamp
)
```

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CINDER_SECRET` | Recommended | JWT signing secret. If not set, a random secret is generated on each startup (tokens won't survive restarts). |
| **Database** | | |
| `CINDER_DATABASE_URL` | Optional | Database URL — highest priority, overrides all other DB config. |
| `DATABASE_URL` | Optional | Standard PaaS convention (Railway, Render, Heroku, Neon, Supabase). Second priority after `CINDER_DATABASE_URL`. |
| `CINDER_DB_POOL_MIN` | Optional | Minimum pool connections for PostgreSQL/MySQL (default: `1`). |
| `CINDER_DB_POOL_MAX` | Optional | Maximum pool connections for PostgreSQL/MySQL (default: `10`). |
| `CINDER_DB_POOL_TIMEOUT` | Optional | Seconds to wait for a free pool connection (default: `30`). |
| `CINDER_DB_CONNECT_TIMEOUT` | Optional | Seconds to open a new connection (default: `10`). |
| **Redis** | | |
| `CINDER_REDIS_URL` | Optional | Redis connection string (e.g. `redis://localhost:6379/0`). Enables Redis-backed cache, rate-limit, and realtime broker. |
| **Cache** | | |
| `CINDER_CACHE_ENABLED` | Optional | `true`/`false`. Auto-enabled when `CINDER_REDIS_URL` is set. |
| `CINDER_CACHE_TTL` | Optional | Default cache TTL in seconds (default: `300`). |
| `CINDER_CACHE_PREFIX` | Optional | Redis key namespace prefix (default: `cinder`). |
| **Rate Limiting** | | |
| `CINDER_RATE_LIMIT_ENABLED` | Optional | `true`/`false` (default: `true`). |
| `CINDER_RATE_LIMIT_ANON` | Optional | Anonymous rate limit as `requests/window_seconds` (default: `100/60`). |
| `CINDER_RATE_LIMIT_USER` | Optional | Authenticated rate limit as `requests/window_seconds` (default: `1000/60`). |
| **Realtime** | | |
| `CINDER_REALTIME_BROKER` | Optional | `memory` (default) or `redis`. Set to `redis` to enable multi-process realtime fan-out. |
| `CINDER_SSE_HEARTBEAT` | Optional | Seconds between SSE ping heartbeat comments (default: `15`). |
| **Email** | | |
| `CINDER_EMAIL_FROM` | Optional | Default sender address for all outbound emails (default: `noreply@localhost`). |
| `CINDER_APP_NAME` | Optional | App name shown in built-in email templates (default: `Your App`). |
| `CINDER_BASE_URL` | Optional | Base URL prepended to verification and password-reset links (default: `http://localhost:8000`). |

### `.env` File

Cinder automatically loads a `.env` file from the current working directory on import:

```env
CINDER_SECRET=your-secret-key-here
```

Generate a secure secret:

```bash
cinder generate-secret
```

### Database

SQLite is the zero-config default. Pass a URL or bare path:

```python
app = Cinder(database="app.db")                           # SQLite (relative path)
app = Cinder(database="sqlite:///app.db")                 # SQLite (explicit scheme)
app = Cinder(database="postgresql://user:pass@host/db")   # PostgreSQL
app = Cinder(database="mysql://user:pass@host/db")        # MySQL
```

In production, set `DATABASE_URL` (or `CINDER_DATABASE_URL`) in your environment — it always overrides the programmatic value. See the [Database](#database) section for the full guide, environment variables, and custom backend API.

---

## Roadmap

- **Phase 3** — Hooks & Lifecycle Events ✅
- **Phase 4** — File Storage (local + S3-compatible) ✅
- **Phase 5** — Email & Notifications ✅
- **Phase 6** — Realtime (WebSocket + SSE) ✅
- **Phase 8** — Redis & Caching ✅
- **Multi-Database Support** — PostgreSQL, MySQL, pluggable backends, env-var database switching ✅
- **OpenAPI / Swagger** — `GET /openapi.json`, Swagger UI, ReDoc ✅
- **Schema Migrations** — `cinder migrate`, version-tracked migration files, auto-generate from schema diff, rollback ✅
- **CLI Improvements** — `generate-secret`, `doctor`, `routes`, `info`, `migrate` sub-app ✅

---

## License

MIT
