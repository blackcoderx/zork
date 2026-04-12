---
title: "Docker"
description: "Deploy your Cinder app with Docker and docker-compose"
sidebar:
  order: 2
---

Docker is the most portable deployment option. Use it for self-hosted servers, VMs, or as the base for any container platform.

---

## Generate the files

```bash
cinder deploy --platform docker --app main.py
```

This creates:

- `Dockerfile` — multi-stage production image
- `docker-compose.yml` — local and production orchestration
- `.dockerignore` — keeps the image lean
- `cinder.toml` — deployment record

---

## Dockerfile

The generated Dockerfile uses a multi-stage build with [uv](https://docs.astral.sh/uv/) for fast, reproducible installs:

```dockerfile
# --- Build stage ---
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

COPY . .

# --- Runtime stage ---
FROM python:3.12-slim

RUN groupadd -r cinder && useradd -r -g cinder -u 1001 cinder

WORKDIR /app
COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

USER cinder
EXPOSE 8000

CMD ["sh", "-c", "cinder migrate run --app main.py && gunicorn -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000"]
```

Key decisions:

- **Multi-stage build** — dependencies are installed in the builder stage; the runtime stage copies only the result, keeping the final image small
- **uv** — significantly faster than pip for resolving and installing packages; uses `uv.lock` for reproducibility
- **Non-root user** — the app runs as UID 1001 (`cinder`) for security
- **Migrations on startup** — `cinder migrate run` runs before gunicorn starts, ensuring the schema is always up to date
- **Gunicorn + UvicornWorker** — production-grade process management with async ASGI support

---

## docker-compose.yml

The generated compose file wires your app with the services it needs. If your app uses PostgreSQL and Redis, it looks like this:

```yaml
services:
  myapp:
    build: .
    ports:
      - "8000:8000"
    environment:
      - CINDER_SECRET=${CINDER_SECRET:-changeme}
      - DATABASE_URL=postgresql://cinder:cinder@postgres:5432/cinder
      - CINDER_REDIS_URL=redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=cinder
      - POSTGRES_PASSWORD=cinder
      - POSTGRES_DB=cinder
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cinder"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

If your app only uses SQLite, no Postgres or Redis services are added.

---

## Build and run

```bash
# Build the image
docker build -t myapp .

# Run with docker compose (starts all services)
docker compose up

# Run in the background
docker compose up -d

# View logs
docker compose logs -f myapp
```

---

## Environment variables

Set your environment variables in a `.env` file at the project root. Docker Compose automatically reads it:

```env
CINDER_SECRET=your-secret-key-here
```

For production, prefer injecting secrets via your hosting environment rather than committing a `.env` file.

---

## Customising

**Change the number of workers:**

Edit the `CMD` in the Dockerfile:

```dockerfile
CMD ["sh", "-c", "cinder migrate run --app main.py && gunicorn -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000 --workers 4"]
```

A good starting point is `(2 × CPU cores) + 1`.

**Change the port:**

Update `EXPOSE` and the `--bind` flag in the CMD, then update the `ports` mapping in `docker-compose.yml`.

---

## .dockerignore

The generated `.dockerignore` excludes files that should not be in the image:

```
.venv/
__pycache__/
*.pyc
.git/
.env
*.db
tests/
```

This keeps the image size down and prevents local environment files from leaking into the build.
