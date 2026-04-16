# Project Structure

This guide explains the Zork CLI commands, project layout, and how to organize your application.

## Project Scaffolding

The recommended way to create a new Zork project is using the CLI scaffold command:

```bash
zork init myapp
```

This creates a new directory with the following structure:

```
myapp/
├── main.py       # Your application entry point
├── .env          # Environment variables
└── .gitignore    # Git ignore rules
```

You can then run your app:

```bash
cd myapp
zork serve main.py
```

## Manual Project Setup

If you prefer to set up your project manually, create these files:

### main.py

Your main application file typically looks like this:

```python
from zork import Zork, Collection, TextField, Auth

app = Zork(database="app.db")

# Define your collections
posts = Collection("posts", fields=[
    TextField("title", required=True),
    TextField("body"),
])

# Register with access control
app.register(posts, auth=["read:public", "write:authenticated"])

# Add authentication
auth = Auth(allow_registration=True)
app.use_auth(auth)

if __name__ == "__main__":
    app.serve()
```

### .env

Store your secrets and configuration:

```bash
ZORK_SECRET=your-secret-key-here
ZORK_DATABASE_URL=app.db
```

### Running the Application

Start the development server:

```bash
zork serve main.py
```

With auto-reload for development:

```bash
zork serve main.py --reload
```

## CLI Commands

Zork provides several CLI commands for development and deployment.

### serve

Start the development server:

```bash
zork serve main.py
```

Options:

- `--reload` — Enable auto-reload when files change
- `--host` — Host to bind to (default: 0.0.0.0)
- `--port` — Port to bind to (default: 8000)

Example:

```bash
zork serve main.py --reload --port 3000
```

### init

Scaffold a new project:

```bash
zork init myapp
```

### generate-secret

Generate a secure random secret key for JWT tokens:

```bash
zork generate-secret
```

Use this output for your `ZORK_SECRET` environment variable.

### routes

List all registered routes in your application:

```bash
zork routes --app main.py
```

Example output:

```
Method               Path                                              Name
---------------------------------------------------------------------------
GET                  /                                                 index
GET                  /api/health                                       health
GET                  /api/posts                                        list_posts
POST                 /api/posts                                        create_posts
GET                  /api/posts/{id}                                   get_posts
PATCH                /api/posts/{id}                                   update_posts
DELETE               /api/posts/{id}                                   delete_posts
GET                  /api/auth/me                                      auth_me
POST                 /api/auth/login                                   auth_login
POST                 /api/auth/logout                                  auth_logout
POST                 /api/auth/register                                auth_register
WS                   /api/realtime                                     realtime
```

### info

Display information about your application:

```bash
zork info --app main.py
```

Example output:

```
Title:            My App
Version:          1.0.0
Python version:   3.11.5
Zork version:    0.1.0
Database:        app.db
Collections (2):  posts, comments
Auth:            enabled
Storage:         LocalFileBackend
Realtime broker: RealtimeBroker
```

### doctor

Check connectivity to configured services:

```bash
zork doctor --app main.py
```

This verifies database and Redis connections are working.

### deploy

Generate deployment configuration files. See the [Deployment](/deployment/overview) guide for details.

```bash
zork deploy docker --app main.py
zork deploy railway --app main.py
zork deploy render --app main.py
zork deploy fly --app main.py
```

## Database Files

Zork creates the following database files:

| File | Purpose |
|------|---------|
| `app.db` | Your main application database (default name) |
| `migrations/` | Schema migration files (if using migrations) |

The database contains your collection tables plus Zork system tables:

| Table | Purpose |
|-------|---------|
| `_users` | User accounts |
| `_token_blocklist` | Revoked JWT tokens |
| `_refresh_tokens` | Refresh token storage |
| `_password_resets` | Password reset tokens |
| `_email_verifications` | Email verification tokens |
| `_schema_migrations` | Applied migration records |

## Directory Layout Options

Here are common ways to organize larger Zork projects:

### Simple Layout

For small to medium projects:

```
myapp/
├── main.py           # All collections defined here
├── .env
└── app.db            # SQLite database
```

### Modular Layout

For larger projects with multiple files:

```
myapp/
├── main.py           # App initialization and serve()
├── models/
│   ├── __init__.py
│   ├── posts.py      # Posts collection
│   └── users.py      # User-related code
├── auth.py           # Auth configuration
├── .env
└── app.db
```

In `main.py`:

```python
from zork import Zork, Auth
from models import posts, comments

app = Zork(database="app.db")
app.register(posts)
app.register(comments)

auth = Auth(allow_registration=True)
app.use_auth(auth)

if __name__ == "__main__":
    app.serve()
```

## Environment Variables

Zork reads configuration from environment variables. Common variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `ZORK_SECRET` | JWT signing secret | Auto-generated (not persistent) |
| `ZORK_DATABASE_URL` | Database connection URL | `app.db` |
| `ZORK_REDIS_URL` | Redis connection URL | Not set |
| `ZORK_AUTH_DELIVERY` | Token delivery mode | `bearer` |
| `DATABASE_URL` | Fallback database URL | `app.db` |

See the [Environment Variables](/deployment/environment-variables) reference for the complete list.

## Next Steps

- [Collections](/core-concepts/collections) — Define your data schemas
- [Authentication](/authentication/setup) — Configure user authentication
- [Deployment](/deployment/overview) — Deploy to production
