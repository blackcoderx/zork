---
title: CLI Commands
description: All Cinder CLI commands and their options
---

The `cinderapi` CLI is installed alongside the framework and provides commands for running your app, managing migrations, and inspecting the application.

## `cinderapi serve`

Start the development server.

```bash
cinderapi serve main.py
cinderapi serve main.py --reload
cinderapi serve main.py --host 0.0.0.0 --port 8080
```

| Option | Default | Description |
|--------|---------|-------------|
| `APP_PATH` | — | Path to the Python file containing the `Cinder` instance |
| `--reload` | `false` | Enable auto-reload on file changes (development only) |
| `--host` | `0.0.0.0` | Host to bind to |
| `--port` | `8000` | Port to listen on |

---

## `cinderapi init`

Scaffold a new Cinder project.

```bash
cinderapi init myapp
```

Creates a `myapp/` directory with:
- `main.py` — starter app with a `posts` collection and auth
- `.env` — environment file template
- `.gitignore` — ignores `*.db`, `.env`, and `__pycache__`

---

## `cinderapi promote`

Promote a user to a new role.

```bash
cinderapi promote alice@example.com
cinderapi promote alice@example.com --role moderator
cinderapi promote alice@example.com --database prod.db
```

| Option | Default | Description |
|--------|---------|-------------|
| `EMAIL` | — | Email address of the user to promote |
| `--role` | `admin` | Role to assign |
| `--database` | `app.db` | Path to the SQLite database file |

---

## `cinderapi generate-secret`

Generate a cryptographically secure secret key for `CINDER_SECRET`.

```bash
cinderapi generate-secret
# Output: a3f8b2c1d4e5...
```

Copy the output into your `.env` file.

---

## `cinderapi doctor`

Check connectivity to configured services.

```bash
cinderapi doctor
cinderapi doctor --app main.py
cinderapi doctor --database postgresql://user:pass@localhost/mydb
```

Checks:
- Database connection
- Redis connection (if `CINDER_REDIS_URL` is set)

---

## `cinderapi routes`

List all registered routes for your app.

```bash
cinderapi routes --app main.py
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

## `cinderapi info`

Show a summary of the application configuration.

```bash
cinderapi info --app main.py
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

## `cinderapi deploy`

Generate deployment configuration files for your app. See [Deployment](/deployment/) for full documentation.

```bash
cinderapi deploy --platform docker
cinderapi deploy --platform railway --app main.py
cinderapi deploy --platform render --dry-run
cinderapi deploy --platform fly --force
cinderapi deploy  # auto-detects platform from environment
```

| Option | Default | Description |
|--------|---------|-------------|
| `--platform`, `-p` | auto-detect | Target platform: `docker`, `railway`, `render`, `fly` |
| `--app` | `main.py` | Path to the file containing the `Cinder` instance |
| `--dry-run` | `false` | Print generated files without writing them |
| `--force` | `false` | Overwrite existing files without prompting |

Platform auto-detection reads `RAILWAY_ENVIRONMENT`, `RENDER`, and `FLY_APP_NAME` from the environment. Defaults to `docker` if none are set.

---

## `cinderapi migrate`

Apply pending migrations. See [Migrations](/migrations/commands/) for full documentation.

```bash
cinderapi migrate
cinderapi migrate --app main.py
cinderapi migrate --dir custom/migrations
```

### Sub-commands

| Command | Description |
|---------|-------------|
| `cinderapi migrate run` | Apply all pending migrations (same as `cinderapi migrate`) |
| `cinderapi migrate status` | Show the status of all migrations |
| `cinderapi migrate create <name>` | Create a new blank migration file |
| `cinderapi migrate create <name> --auto` | Auto-generate migration from schema diff |
| `cinderapi migrate rollback` | Roll back the last applied migration |
