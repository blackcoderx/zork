# Quick Start

This guide walks you through creating a fully working REST API with authentication in under 10 minutes. By the end, you will have a running API with user authentication and CRUD operations.

## Prerequisites

Make sure you have Zork installed. If you have not installed it yet, see the [Installation](/getting-started/installation) guide.

## Step 1: Create Your Application File

Create a new file called `main.py` in your project directory:

```python
from zork import Zork, Collection, TextField, IntField, Auth

app = Zork(database="app.db")

posts = Collection("posts", fields=[
    TextField("title", required=True),
    TextField("body"),
    IntField("views", default=0),
])

auth = Auth(token_expiry=86400, allow_registration=True)

app.register(posts, auth=["read:public", "write:authenticated"])
app.use_auth(auth)

if __name__ == "__main__":
    app.serve()
```

## Step 2: Start the Server

Run the following command in your terminal:

```bash
zork serve main.py
```

You should see output indicating the server is running:

```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

The server starts on port 8000 by default.

For development with automatic code reloading when files change:

```bash
zork serve main.py --reload
```

## Step 3: Explore Your API

Zork automatically generates REST endpoints for your collections and authentication.

### Authentication Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register a new user account |
| POST | `/api/auth/login` | Log in and receive a JWT token |
| GET | `/api/auth/me` | Get the current authenticated user |
| POST | `/api/auth/logout` | Log out and revoke the token |
| POST | `/api/auth/refresh` | Get a new access token |

### Posts Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/posts` | List all posts |
| POST | `/api/posts` | Create a new post |
| GET | `/api/posts/{id}` | Get a single post |
| PATCH | `/api/posts/{id}` | Update a post |
| DELETE | `/api/posts/{id}` | Delete a post |

### System Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check endpoint |
| GET | `/openapi.json` | OpenAPI 3.1 schema |
| GET | `/docs` | Swagger UI documentation |

## Step 4: Test Your API

You can test your API using curl or any HTTP client.

### Register a User

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "secret123"}'
```

The response includes the user data and an access token:

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": "abc-123-def",
    "email": "alice@example.com",
    "role": "user",
    "is_verified": false
  }
}
```

### Create a Post

Replace `YOUR_TOKEN_HERE` with the token from the registration response:

```bash
curl -X POST http://localhost:8000/api/posts \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"title": "Hello Zork", "body": "My first post content"}'
```

### List Posts

Anyone can read posts without authentication:

```bash
curl http://localhost:8000/api/posts
```

The response includes your posts in a paginated format:

```json
{
  "items": [
    {
      "id": "xyz-789-abc",
      "title": "Hello Zork",
      "body": "My first post content",
      "views": 0,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

## Step 5: View API Documentation

Open your browser and navigate to:

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- OpenAPI Schema: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

The Swagger UI provides an interactive interface where you can explore and test all endpoints.

## What Just Happened

In this quick start, you created a Zork application that includes:

- **Automatic database table creation** — The `posts` collection automatically created a table with `id`, `title`, `body`, `views`, `created_at`, and `updated_at` columns.

- **JWT authentication** — The `Auth` class set up user registration, login, and token management with secure JWT tokens.

- **Access control** — The `auth` parameter on `app.register()` protected write operations so only authenticated users can create posts.

- **RESTful endpoints** — All CRUD operations are available at predictable URL patterns following REST conventions.

## Next Steps

Now that you have a working API, explore these topics:

- [Collections](/core-concepts/collections) — Learn about more field types and collection options
- [Field Types](/core-concepts/fields) — Explore all available field types
- [Access Control](/core-concepts/access-control) — Fine-tune who can access your data
- [Authentication](/authentication/setup) — Configure authentication options
- [Deployment](/deployment/overview) — Deploy your API to production
