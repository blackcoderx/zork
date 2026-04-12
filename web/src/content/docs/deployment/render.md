---
title: "Render"
description: "Deploy your Cinder app to Render"
sidebar:
  order: 4
---

[Render](https://render.com) supports infrastructure-as-code via a `render.yaml` blueprint file. Define your web service, database, and Redis in one file and Render provisions everything automatically.

---

## Generate the config

```bash
cinder deploy --platform render --app main.py
```

This creates:

- `render.yaml` — blueprint defining all services
- `cinder.toml` — deployment record

---

## `render.yaml`

```yaml
services:
  - type: web
    name: myapp
    runtime: python
    buildCommand: pip install uv && uv sync --frozen --no-dev
    startCommand: cinder migrate run --app main.py && gunicorn -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:$PORT
    healthCheckPath: /api/health
    envVars:
      - key: CINDER_SECRET
        generateValue: true
      - key: PYTHON_VERSION
        value: "3.12"
      - key: DATABASE_URL
        fromDatabase:
          name: myapp-db
          property: connectionString

databases:
  - name: myapp-db
    plan: free

keyvalues:
  - name: myapp-redis
    plan: free
```

Key things to know:

- `generateValue: true` — Render auto-generates a random value for `CINDER_SECRET` and keeps it stable across deploys. You don't need to set it manually.
- `fromDatabase` — wires the Postgres connection string directly from the database service. No copy-pasting URLs.
- `fromService` — same pattern for Redis, using the `keyvalue` service type.
- `databases` and `keyvalues` sections are only generated if your app needs them.

---

## Deploy

1. **Push `render.yaml` to your GitHub repo**
2. Go to the [Render dashboard](https://dashboard.render.com) → **New** → **Blueprint**
3. Connect your repo — Render reads `render.yaml` and creates all services
4. Render deploys automatically on every push to your main branch

That's it. `CINDER_SECRET` is auto-generated, the database URL is wired automatically, and migrations run on startup via the start command.

---

## Health checks

Render uses `healthCheckPath: /api/health` to route traffic only after your app passes the health check. Cinder exposes this at `GET /api/health` with no configuration needed.

---

## Environment variables

Most variables are wired automatically via `render.yaml`. If you need to add more:

1. Go to your web service in the Render dashboard
2. Click **Environment** → **Add Environment Variable**

Common additions:

| Variable | Example |
|----------|---------|
| `CINDER_EMAIL_FROM` | `no-reply@myapp.com` |
| `CINDER_APP_NAME` | `MyApp` |
| `CINDER_BASE_URL` | `https://myapp.onrender.com` |

---

## Free tier notes

Render's free tier spins down web services after 15 minutes of inactivity. The first request after a spin-down takes a few seconds while the service restarts. For always-on apps, upgrade to a paid instance type.

Free PostgreSQL databases on Render expire after 90 days. For production, use a paid database plan.
