# Caching Setup

Zork includes a caching system to improve API performance by storing responses and serving them without hitting the database.

## Overview

The cache system implements cache-aside pattern for collection GET requests:

1. On cache miss, the request goes to the database
2. The response is stored in the cache
3. On cache hit, the cached response is returned immediately

## Enabling Cache

Caching is enabled automatically when Redis is configured:

```python
app.configure_redis(url="redis://localhost:6379/0")
```

Or enable manually:

```python
from zork import Zork
from zork.cache import MemoryCacheBackend

app = Zork()
app.cache.use(MemoryCacheBackend())
```

## Cache Backends

### Memory Cache

In-memory cache for single-process applications:

```python
from zork.cache import MemoryCacheBackend

app.cache.use(MemoryCacheBackend())
```

Best for:

- Development and testing
- Single-server deployments
- Low-traffic applications

Note: Memory cache is not shared between processes and is cleared on restart.

### Redis Cache

Redis-backed cache for production:

```python
app.configure_redis(url="redis://localhost:6379/0")
```

Benefits:

- Shared across all server processes
- Persistent across restarts
- High performance

## Cache Configuration

### TTL (Time-to-Live)

Set how long cached responses are stored:

```python
app.cache.configure(default_ttl=300)  # Cache for 5 minutes
```

### Per-User Caching

By default, cache keys include the user ID so users only see their own data:

```python
app.cache.configure(per_user=True)  # Default
```

For shared cache across users (public data):

```python
app.cache.configure(per_user=False)
```

### Excluding Paths

Exclude specific paths from caching:

```python
app.cache.exclude("/api/health")
app.cache.exclude("/api/search")
```

## How It Works

### Cache Keys

Cache keys are generated from:

- Collection name
- Operation (list or get)
- Request parameters
- User ID (if per_user is enabled)

Example cache key:

```
response:posts:list:a1b2c3d4...
```

### Cached Operations

Only GET requests are cached:

- `GET /api/posts` (list)
- `GET /api/posts/{id}` (single record)

### Cache Headers

Cached responses include an `X-Cache` header:

```
X-Cache: HIT
X-Cache: MISS
```

### Cache Invalidation

Cache is automatically invalidated when:

- A record is created
- A record is updated
- A record is deleted

The cache key for the affected collection is invalidated on mutations.

## Disabling Cache

Disable caching entirely:

```python
app.cache.enable(False)
```

Or via environment variable:

```bash
ZORK_CACHE_ENABLED=false
```

## Using Cache in Hooks

Access the cache directly from hooks:

```python
@app.on("app:startup")
async def warm_cache(ctx):
    # Fetch and cache popular items
    posts = await get_popular_posts()
    for post in posts:
        await app.cache.backend.set(
            f"popular:{post['id']}",
            json.dumps(post).encode(),
            ttl=3600
        )
```

## Custom Cache Backend

Create a custom cache backend:

```python
from zork.cache import CacheBackend

class MyCacheBackend(CacheBackend):
    async def get(self, key):
        # Get from your cache
        pass
    
    async def set(self, key, value, ttl):
        # Store in your cache
        pass
    
    # ... implement other methods
```

Then use it:

```python
app.cache.use(MyCacheBackend())
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ZORK_CACHE_ENABLED` | Enable/disable caching | true |
| `ZORK_CACHE_TTL` | Default cache TTL | 300 |
| `ZORK_REDIS_URL` | Redis URL | - |

## Performance Tips

### Cache Frequently Accessed Data

Good candidates for caching:

- List endpoints with filters
- Expensive queries
- Data that rarely changes

### Set Appropriate TTLs

- Short TTL for frequently changing data
- Longer TTL for static content

### Exclude Expensive Operations

Exclude expensive operations that should not be cached:

```python
app.cache.exclude("/api/reports/generate")
```

## Next Steps

- [Cache Invalidation](/caching/invalidation) — Understanding invalidation
- [Rate Limiting](/rate-limiting/setup) — Protect your API
