---
title: Environment Variables Reference
description: Complete reference for Zork environment variables
---

# Environment Variables Reference

This is a comprehensive reference for all environment variables used by Zork.

## Core Variables

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `ZORK_SECRET` | For auth | JWT signing secret | — |
| `ZORK_DATABASE_URL` | No | Database connection URL | `app.db` |
| `ZORK_REDIS_URL` | No | Redis connection URL | — |
| `ZORK_REALTIME_BROKER` | No | Realtime broker type | `inprocess` |

## Database

### Connection

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Fallback database URL (PaaS) | `app.db` |
| `ZORK_AUTO_SYNC` | Auto-sync schema on startup | auto-detect |

### PostgreSQL Pool Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `ZORK_DB_POOL_MIN` | Minimum connections | `1` |
| `ZORK_DB_POOL_MAX` | Maximum connections | `10` |
| `ZORK_DB_TIMEOUT` | Connection timeout (seconds) | `30` |
| `ZORK_DB_CONNECT_TIMEOUT` | Connect timeout (seconds) | `10` |

## Authentication

### Token Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `ZORK_ACCESS_TOKEN_EXPIRY` | Access token lifetime (seconds) | `3600` |
| `ZORK_REFRESH_TOKEN_EXPIRY` | Refresh token lifetime (seconds) | `604800` |
| `ZORK_AUTH_DELIVERY` | Token delivery mechanism | `bearer` |
| `ZORK_MAX_REFRESH_TOKENS` | Max refresh tokens per user | `5` |

### Cookie Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `ZORK_COOKIE_SECURE` | Require HTTPS | `true` |
| `ZORK_COOKIE_SAMESITE` | SameSite policy | `lax` |
| `ZORK_COOKIE_DOMAIN` | Cookie domain | `None` |
| `ZORK_CSRF_ENABLE` | CSRF protection | `true` |

### Blocklist

| Variable | Description | Default |
|----------|-------------|---------|
| `ZORK_BLOCKLIST_BACKEND` | Blocklist backend | `database` |

## Caching

| Variable | Description | Default |
|----------|-------------|---------|
| `ZORK_CACHE_ENABLED` | Enable caching | `true` |
| `ZORK_CACHE_TTL` | Default TTL (seconds) | `300` |
| `ZORK_CACHE_PREFIX` | Redis key prefix | `zork` |

## Rate Limiting

| Variable | Description | Default |
|----------|-------------|---------|
| `ZORK_RATE_LIMIT_ENABLED` | Enable rate limiting | `true` |
| `ZORK_RATE_LIMIT_ANON` | Anonymous limit | `100/60` |
| `ZORK_RATE_LIMIT_USER` | Authenticated limit | `1000/60` |

## Email

| Variable | Description | Default |
|----------|-------------|---------|
| `ZORK_EMAIL_FROM` | Email from address | `noreply@localhost` |
| `ZORK_APP_NAME` | App name for emails | `Your App` |
| `ZORK_BASE_URL` | Base URL for email links | `http://localhost:8000` |

## Realtime

| Variable | Description | Default |
|----------|-------------|---------|
| `ZORK_REALTIME_BROKER` | Broker type | `inprocess` |
| `ZORK_SSE_HEARTBEAT` | SSE heartbeat (seconds) | `15` |

## Logging

| Variable | Description | Default |
|----------|-------------|---------|
| `ZORK_LOG_LEVEL` | Minimum log level | `INFO` |
| `ZORK_LOG_FORMAT` | Output format (`console`, `json`) | `console` |
| `ZORK_LOG_COLORIZE` | Enable ANSI colors (`auto`, `true`, `false`) | `auto` |
| `ZORK_LOG_INCLUDE_TIMESTAMP` | Include ISO timestamp | `true` |
| `ZORK_LOG_INCLUDE_MODULE` | Include logger name | `true` |

### Development

```bash
# Verbose, colored output
ZORK_LOG_LEVEL=DEBUG ZORK_LOG_COLORIZE=true python main.py
```

### Production

```bash
# JSON output for log aggregation
ZORK_LOG_FORMAT=json ZORK_LOG_LEVEL=INFO python main.py
```

Some platforms use these standard variable names as fallbacks:

| Variable | Zork Equivalent |
|----------|----------------|
| `DATABASE_URL` | `ZORK_DATABASE_URL` |
| `REDIS_URL` | `ZORK_REDIS_URL` |

## Usage Examples

### SQLite (Development)

```bash
# No environment variables needed for SQLite
ZORK_SECRET=your-secret-key
```

### PostgreSQL (Production)

```bash
ZORK_SECRET=your-secret-key
ZORK_DATABASE_URL=postgresql://user:pass@localhost:5432/mydb
ZORK_DB_POOL_MAX=20
```

### With Redis

```bash
ZORK_SECRET=your-secret-key
ZORK_DATABASE_URL=postgresql://user:pass@localhost:5432/mydb
ZORK_REDIS_URL=redis://localhost:6379/0
```

### Auth with Cookies

```bash
ZORK_SECRET=your-secret-key
ZORK_AUTH_DELIVERY=cookie
ZORK_COOKIE_SECURE=true
ZORK_COOKIE_SAMESITE=lax
```

### Rate Limiting

```bash
ZORK_SECRET=your-secret-key
ZORK_RATE_LIMIT_ANON=50/60
ZORK_RATE_LIMIT_USER=500/60
```

### Email (Production)

```bash
ZORK_SECRET=your-secret-key
ZORK_EMAIL_FROM=noreply@example.com
ZORK_APP_NAME=My Application
ZORK_BASE_URL=https://api.example.com
```

## Generating Secrets

Generate a secure JWT secret:

```bash
zork generate-secret
```

Use the output:

```bash
ZORK_SECRET=<generated-secret>
```

## Platform-Specific Notes

### Docker Compose

The generated `docker-compose.yml` sets these automatically:

```yaml
environment:
  - ZORK_SECRET=${ZORK_SECRET:-changeme}
  - DATABASE_URL=postgresql://zork:zork@postgres:5432/zork
  - ZORK_REDIS_URL=redis://redis:6379/0
```

### Railway

Set via dashboard or `railway.toml`:

```toml
[deploy]
  environment:
    - ZORK_SECRET = ${ZORK_SECRET}
```

### Render

The `render.yaml` auto-generates secrets:

```yaml
envVars:
  - key: ZORK_SECRET
    generateValue: true
```

### Fly.io

Set via CLI:

```bash
fly secrets set ZORK_SECRET=$(zork generate-secret)
```

## Security Notes

- **Never commit secrets** to version control
- Use environment files (`.env`) locally, but add to `.gitignore`
- Use secret management in production (platforms handle this)
- Rotate secrets regularly:

```bash
# Generate new secret
zork generate-secret

# Update in production
fly secrets set ZORK_SECRET=new-secret
# or
zork deploy render  # Regenerate config
```

## Validation

Check your environment:

```bash
zork doctor
```

This checks:
- Required variables are set
- Database connection works
- Redis connection works (if configured)
- Secret is properly formatted

## Next Steps

- [Docker Deployment](/deployment/docker)
- [Railway Deployment](/deployment/railway)
- [Render Deployment](/deployment/render)
- [Fly.io Deployment](/deployment/flyio)