---
title: Configuration
description: Configure caching backends and options
sidebar:
  order: 2
---

## Backends

### Redis (recommended for production)

```python
from cinder.cache.backends import RedisCacheBackend

app.cache.use(RedisCacheBackend())
```

Requires `pip install "cinder[redis]"`. Reads the Redis URL from `CINDER_REDIS_URL` automatically.

Custom URL:

```python
app.cache.use(RedisCacheBackend(prefix="myapp"))
app.configure_redis(url="redis://localhost:6379")
```

### In-memory (development / single process)

```python
from cinder.cache.backends import MemoryCacheBackend

app.cache.use(MemoryCacheBackend())
app.cache.enable()
```

The in-memory cache is a simple dict. It is not shared across processes and is cleared on restart. Suitable for development and testing only.

## Fluent configuration API

```python
app.cache \
    .use(RedisCacheBackend()) \
    .configure(default_ttl=300, per_user=True) \
    .exclude("/api/health", "/api/docs")
```

### `.use(backend)`

Plug in a cache backend. Must be called before `app.build()` or `app.serve()`.

### `.configure(default_ttl, per_user)`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `default_ttl` | `int` | `300` | Seconds before cached entries expire |
| `per_user` | `bool` | `True` | Cache responses separately per user. Ensures `read:owner` rules are respected. |

Also configurable via environment variable:

```dotenv
CINDER_CACHE_TTL=600
```

### `.exclude(*paths)`

Never cache responses for these path prefixes:

```python
app.cache.exclude("/api/admin", "/api/realtime")
```

### `.enable(value=True)`

Force caching on or off regardless of whether Redis is configured:

```python
app.cache.enable(True)    # always on
app.cache.enable(False)   # always off
```

Also configurable via:

```dotenv
CINDER_CACHE_ENABLED=true
CINDER_CACHE_ENABLED=false
```

## Cache key prefix

When using Redis, all cache keys are prefixed to avoid collisions with other applications:

```dotenv
CINDER_CACHE_PREFIX=myapp   # default: "cinder"
```

## Auto-detection

If you don't explicitly call `.use()`, Cinder picks the backend automatically:

1. If `CINDER_REDIS_URL` is set → `RedisCacheBackend`
2. Otherwise → `MemoryCacheBackend`

Caching is only activated if `CINDER_REDIS_URL` is set or you call `.enable()` explicitly.
