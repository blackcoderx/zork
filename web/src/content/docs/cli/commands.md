---
title: CLI Commands
description: All Cinder CLI commands and their options
---

The `cinder` CLI is installed alongside the framework and provides commands for running your app, managing migrations, and inspecting the application.

## `cinder serve`

Start the development server.

```bash
cinder serve main.py
cinder serve main.py --reload
cinder serve main.py --host 0.0.0.0 --port 8080
```

| Option | Default | Description |
|--------|---------|-------------|
| `APP_PATH` | — | Path to the Python file containing the `Cinder` instance |
| `--reload` | `false` | Enable auto-reload on file changes (development only) |
| `--host` | `0.0.0.0` | Host to bind to |
| `--port` | `8000` | Port to listen on |

---

## `cinder init`

Scaffold a new Cinder project.

```bash
cinder init myapp
```

Creates a `myapp/` directory with:
- `main.py` — starter app with a `posts` collection and auth
- `.env` — environment file template
- `.gitignore` — ignores `*.db`, `.env`, and `__pycache__`

---

## `cinder promote`

Promote a user to a new role.

```bash
cinder promote alice@example.com
cinder promote alice@example.com --role moderator
cinder promote alice@example.com --database prod.db
```

| Option | Default | Description |
|--------|---------|-------------|
| `EMAIL` | — | Email address of the user to promote |
| `--role` | `admin` | Role to assign |
| `--database` | `app.db` | Path to the SQLite database file |

---

## `cinder generate-secret`

Generate a cryptographically secure secret key for `CINDER_SECRET`.

```bash
cinder generate-secret
# Output: a3f8b2c1d4e5...
```

Copy the output into your `.env` file.

---

## `cinder doctor`

Check connectivity to configured services.

```bash
cinder doctor
cinder doctor --app main.py
cinder doctor --database postgresql://user:pass@localhost/mydb
```

Checks:
- Database connection
- Redis connection (if `CINDER_REDIS_URL` is set)

---

## `cinder routes`

List all registered routes for your app.

```bash
cinder routes --app main.py
```

Output:

```
Method               Path                                               Name
---------------------------------------------------------------------------
GET                  /                                                  index
GET                  /api/health                                        health
GET                  /api/posts                                         posts_list
POST                 /api/posts                                         posts_create
GET                  /api/posts/{id}                                    posts_get
PATCH                /api/posts/{id}                                    posts_update
DELETE               /api/posts/{id}                                    posts_delete
...
```

---

## `cinder info`

Show a summary of the application configuration.

```bash
cinder info --app main.py
```

Output:

```
Title:            My API
Version:          1.0.0
Python version:   3.12.0
Cinder version:   0.1.0
Database:         app.db
Collections (2):  posts, comments
Auth:             enabled
Storage:          LocalFileBackend
Realtime broker:  RealtimeBroker
```

---

## `cinder deploy`

Generate deployment configuration files for your app. See [Deployment](/deployment/) for full documentation.

```bash
cinder deploy --platform docker
cinder deploy --platform railway --app main.py
cinder deploy --platform render --dry-run
cinder deploy --platform fly --force
cinder deploy  # auto-detects platform from environment
```

| Option | Default | Description |
|--------|---------|-------------|
| `--platform`, `-p` | auto-detect | Target platform: `docker`, `railway`, `render`, `fly` |
| `--app` | `main.py` | Path to the file containing the `Cinder` instance |
| `--dry-run` | `false` | Print generated files without writing them |
| `--force` | `false` | Overwrite existing files without prompting |

Platform auto-detection reads `RAILWAY_ENVIRONMENT`, `RENDER`, and `FLY_APP_NAME` from the environment. Defaults to `docker` if none are set.

---

## `cinder migrate`

Apply pending migrations. See [Migrations](/migrations/commands/) for full documentation.

```bash
cinder migrate
cinder migrate --app main.py
cinder migrate --dir custom/migrations
```

### Sub-commands

| Command | Description |
|---------|-------------|
| `cinder migrate run` | Apply all pending migrations (same as `cinder migrate`) |
| `cinder migrate status` | Show the status of all migrations |
| `cinder migrate create <name>` | Create a new blank migration file |
| `cinder migrate create <name> --auto` | Auto-generate migration from schema diff |
| `cinder migrate rollback` | Roll back the last applied migration |
