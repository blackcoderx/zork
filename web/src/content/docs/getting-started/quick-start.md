---
title: Quick Start
description: Build your first Cinder API in under 5 minutes
sidebar:
  order: 2
---

This guide walks you through creating a fully working REST API with authentication in a single Python file.

## 1. Create your app file

Create `main.py`:

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
```

## 2. Start the server

```bash
cinder serve main.py
```

The server starts on `http://localhost:8000`.

For development with auto-reload:

```bash
cinder serve main.py --reload
```

## 3. What you get

Cinder auto-generates the following endpoints:

**Auth**
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/register` | Register a new user |
| `POST` | `/api/auth/login` | Get a JWT token |
| `GET` | `/api/auth/me` | Get the current user |
| `POST` | `/api/auth/logout` | Revoke the current token |
| `POST` | `/api/auth/refresh` | Issue a new token |

**Posts**
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/posts` | List posts (public) |
| `POST` | `/api/posts` | Create a post (auth required) |
| `GET` | `/api/posts/{id}` | Get a single post |
| `PATCH` | `/api/posts/{id}` | Update a post (auth required) |
| `DELETE` | `/api/posts/{id}` | Delete a post (auth required) |

**System**
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/openapi.json` | OpenAPI 3.1 schema |
| `GET` | `/docs` | Swagger UI |

## 4. Try it out

Register a user:

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "secret123"}'
```

```json
{
  "token": "eyJ...",
  "user": { "id": "...", "email": "alice@example.com", "role": "user" }
}
```

Create a post with the token:

```bash
curl -X POST http://localhost:8000/api/posts \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"title": "Hello Cinder", "body": "My first post"}'
```

List posts (no auth required):

```bash
curl http://localhost:8000/api/posts
```

```json
{
  "items": [
    { "id": "...", "title": "Hello Cinder", "body": "My first post", "views": 0, "created_at": "...", "updated_at": "..." }
  ],
  "total": 1,
  "page": 1,
  "per_page": 50
}
```

## 5. Next steps

- [Core Concepts](/core-concepts/app/) — understand how the `Cinder` app works
- [Collections](/core-concepts/collections/) — define richer schemas
- [Field Types](/fields/field-types/) — all available field types and options
- [Access Control](/core-concepts/access-control/) — fine-grained permission rules
