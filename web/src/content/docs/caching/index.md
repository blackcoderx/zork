---
title: Caching
description: Cache API responses to reduce database load
sidebar:
  order: 1
---

Cinder includes a cache-aside middleware that automatically caches `GET` responses and invalidates them on writes. No changes to your collection definitions are needed.

## How it works

1. On `GET /api/{collection}` or `GET /api/{collection}/{id}`, the middleware checks the cache
2. If a cached response exists and is not expired, it is returned immediately (no database query)
3. On `POST`, `PATCH`, or `DELETE`, all cache entries for that collection are invalidated
4. The next read repopulates the cache

## Enabling caching

Caching is **automatically enabled** when `CINDER_REDIS_URL` is set. No code changes needed.

```dotenv
CINDER_REDIS_URL=redis://localhost:6379
```

For development without Redis, use the in-memory cache:

```python
from cinder.cache.backends import MemoryCacheBackend

app.cache.use(MemoryCacheBackend())
app.cache.enable()
```

## Configuration

```python
app.cache.use(RedisCacheBackend())
app.cache.configure(
    default_ttl=300,   # seconds before a cached entry expires
    per_user=True,     # cache separately per authenticated user
)
app.cache.exclude("/api/health")  # never cache these paths
```

## In this section

- [Configuration](/caching/configuration/) — backend setup and tuning options
- [Cache Invalidation](/caching/invalidation/) — how writes clear stale entries
