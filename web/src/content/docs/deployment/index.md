---
title: "Deployment"
description: "Deploy your Cinder app to any platform with a single command"
sidebar:
  order: 1
---

`cinderapi deploy` generates production-ready deployment configuration files for your app. It inspects your Cinder instance to detect which services you need — database, Redis, auth, file storage — and writes platform-specific config tailored to those requirements.

It does **not** deploy your app. It generates the files so you can commit them and let the platform handle the rest.

---

## Before you deploy

Generate a secret key and add it to your `.env` file:

```bash
cinderapi generate-secret
# Copy the output into your .env as CINDER_SECRET
```

This is required for JWT signing. Tokens are invalid without a persistent secret.

---

## Usage

```bash
cinderapi deploy --platform <platform> --app main.py
```

| Option | Default | Description |
|--------|---------|-------------|
| `--platform`, `-p` | auto-detect | `docker`, `railway`, `render`, or `fly` |
| `--app` | `main.py` | Path to the file containing your `Cinder` instance |
| `--dry-run` | `false` | Print generated files to the terminal without writing them |
| `--force` | `false` | Overwrite existing files without prompting |

---

## Platform overview

| Platform | Files generated |
|----------|----------------|
| `docker` | `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `cinder.toml` |
| `railway` | `railway.toml`, `cinder.toml` |
| `render` | `render.yaml`, `cinder.toml` |
| `fly` | `fly.toml`, `Dockerfile`, `.dockerignore`, `cinder.toml` |

---

## App introspection

`cinderapi deploy` loads your app file and inspects it to determine what your app needs:

- **Database type** — reads `CINDER_DATABASE_URL`, `DATABASE_URL`, or the `database=` constructor argument to detect PostgreSQL, MySQL, or SQLite
- **Redis** — checks `CINDER_REDIS_URL` and whether cache, rate-limit, or realtime backends are Redis-backed
- **Auth** — checks if `app.use_auth()` was called
- **File storage** — checks if a storage backend is configured
- **Email** — checks if an email backend is configured

This means the generated configs only include the services your app actually uses — no unnecessary Postgres or Redis services added.

---

## Auto-detection

If you omit `--platform`, Cinder detects it from environment variables:

| Environment variable | Detected platform |
|---------------------|------------------|
| `RAILWAY_ENVIRONMENT` | railway |
| `RENDER` | render |
| `FLY_APP_NAME` | fly |
| _(none set)_ | docker |

---

## Preview before writing

Use `--dry-run` to see exactly what will be generated without touching the filesystem:

```bash
cinderapi deploy --platform railway --dry-run
```

---

## `cinder.toml`

Every platform generates a `cinder.toml` alongside the platform config. This is a central deployment record describing your app's requirements:

```toml
[project]
name = "myapp"
python_version = "3.12"

[deploy]
platform = "railway"
app_path = "main.py"
port = 8000
workers = 4

[services]
database = "postgresql"
redis = true

[health]
path = "/api/health"
interval = 10
timeout = 5
```

---

## SQLite warning

If your app uses SQLite and you target a cloud platform (Railway, Render, Fly), you'll see:

```
Warning: SQLite is not recommended for production on cloud platforms.
Consider switching to PostgreSQL.
```

SQLite is fine for local development but the filesystem is ephemeral on most cloud platforms — your data won't persist across deploys. Switch to PostgreSQL before deploying.

---

## Platform guides

- [Docker](/deployment/docker/)
- [Railway](/deployment/railway/)
- [Render](/deployment/render/)
- [Fly.io](/deployment/fly/)
