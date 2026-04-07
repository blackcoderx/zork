# Cinder

A lightweight, open-source backend framework for Python. Build production-ready REST APIs with built-in auth, dynamic collections, and SQLite persistence — no heavy frameworks required.

Define your data schema in Python, and Cinder auto-generates a full CRUD API with JWT authentication, role-based access control, filtering, pagination, and relation expansion.

## Table of Contents

- [Install](#install)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Field Types](#field-types)
- [Authentication](#authentication)
- [API Endpoints](#api-endpoints)
- [Filtering, Pagination & Sorting](#filtering-pagination--sorting)
- [Relations & Expand](#relations--expand)
- [Middleware](#middleware)
- [CLI](#cli)
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
pip install cinder[s3]      # S3 file storage (boto3)
pip install cinder[email]   # Email delivery (aiosmtplib)
pip install cinder[redis]   # Redis caching & sessions
pip install cinder[ai]      # AI integration (Anthropic)
pip install cinder[all]     # All extras
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

The reset token is currently logged to the console. Email delivery will be added in a future phase.

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

## Middleware

Cinder includes three built-in middleware layers applied to every request:

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

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CINDER_SECRET` | Recommended | JWT signing secret. If not set, a random secret is generated on each startup (tokens won't survive restarts). |

### `.env` File

Cinder automatically loads a `.env` file from the current working directory on import:

```env
CINDER_SECRET=your-secret-key-here
```

Generate a secure secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Database

SQLite is the default (and currently only) database. Pass the file path when creating the app:

```python
app = Cinder(database="app.db")       # Relative path
app = Cinder(database="/data/app.db") # Absolute path
```

Cinder uses WAL mode for better concurrent read performance and enables foreign key enforcement.

---

## Roadmap

See [phases.md](phases.md) for the full roadmap of upcoming features:

- **Phase 3** — Hooks & Lifecycle Events
- **Phase 4** — File Storage (local + S3)
- **Phase 5** — Email & Notifications
- **Phase 6** — Realtime (WebSocket subscriptions)
- **Phase 7** — AI Integration
- **Phase 8** — Redis & Caching

---

## License

MIT
