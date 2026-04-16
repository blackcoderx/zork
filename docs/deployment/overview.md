# Deployment Overview

Zork can be deployed to various platforms. This guide covers deployment options and best practices.

## Deployment Options

Zork supports deployment to:

- [Docker](/deployment/docker) — Containerized deployment
- [Railway](/deployment/railway) — Simple cloud deployment
- [Render](/deployment/render) — Managed hosting
- [Fly.io](/deployment/flyio) — Edge deployment

## CLI Deployment Command

Zork includes a deployment generator:

```bash
zork deploy --platform <platform> --app main.py
```

This generates platform-specific configuration files.

## General Deployment Steps

### 1. Prepare Your Application

Ensure your app is production-ready:

```python
# main.py
from zork import Zork, Collection, TextField, Auth

app = Zork(
    database="app.db",
    title="My API",
    version="1.0.0"
)

# Register collections
posts = Collection("posts", fields=[
    TextField("title", required=True),
    TextField("body"),
])

app.register(posts)

# Add auth
auth = Auth(allow_registration=True)
app.use_auth(auth)
```

### 2. Set Environment Variables

Essential environment variables for production:

```bash
# Required for authentication
ZORK_SECRET=your-secure-secret-key

# Database URL (for production, use PostgreSQL)
DATABASE_URL=postgresql://user:pass@host:5432/db

# Redis URL (optional, for caching/realtime)
ZORK_REDIS_URL=redis://host:6379/0
```

### 3. Generate Secret

```bash
zork generate-secret
```

Use the output as your `ZORK_SECRET`.

### 4. Choose Your Platform

Select the platform that best fits your needs:

| Platform | Best For |
|----------|----------|
| Docker | Maximum control, self-hosting |
| Railway | Quick deployments, minimal config |
| Render | Managed hosting, automatic scaling |
| Fly.io | Global edge deployment |

## Production Checklist

Before deploying:

- Set `ZORK_SECRET` to a secure value
- Use PostgreSQL instead of SQLite for production
- Configure Redis for caching and realtime
- Enable HTTPS
- Set appropriate rate limits
- Test database migrations
- Configure logging
- Set up monitoring

## Running with Gunicorn

For production WSGI servers:

```bash
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
```

With custom host/port:

```bash
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `ZORK_SECRET` | Yes | JWT signing secret |
| `DATABASE_URL` | Yes | Database connection URL |
| `ZORK_REDIS_URL` | No | Redis connection URL |
| `ZORK_AUTH_DELIVERY` | No | Token delivery mode |
| `ZORK_RATE_LIMIT_ENABLED` | No | Enable rate limiting |

## Health Checks

Most platforms require a health check endpoint. Zork provides:

```
GET /api/health
```

Returns:

```json
{
  "status": "ok"
}
```

## Database Considerations

### SQLite Limitations

SQLite is not recommended for production on cloud platforms:

- Limited concurrent writes
- Single-file database on ephemeral filesystem
- No network access (usually)

### PostgreSQL (Recommended)

For production:

```bash
DATABASE_URL=postgresql://user:pass@host:5432/db
```

Many platforms provide managed PostgreSQL databases.

## Next Steps

Choose your deployment platform:

- [Docker Deployment](/deployment/docker)
- [Railway Deployment](/deployment/railway)
- [Render Deployment](/deployment/render)
- [Fly.io Deployment](/deployment/flyio)
