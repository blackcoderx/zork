---
title: Cache Invalidation
description: How writes clear stale cached responses
sidebar:
  order: 3
---

Cinder uses **tag-based invalidation** to clear cache entries when data changes. You don't need to manage this manually.

## How it works

Each cache entry is tagged with the collection name. When a write operation (`POST`, `PATCH`, `DELETE`) completes, the invalidation hooks fire and clear all cache entries tagged with that collection.

This means:

- A new post → all `/api/posts` list responses are evicted
- An updated post → all `/api/posts` list responses + the specific `/api/posts/{id}` response are evicted
- A deleted post → same as update

## Automatic setup

Cache invalidation is wired automatically when caching is enabled. The `install_invalidation()` call in `app.build()` registers `after_create`, `after_update`, and `after_delete` hooks on every registered collection.

## Cross-collection invalidation

If you have a collection whose cached responses depend on data from another collection (e.g. a `posts` list that embeds author names), you can manually evict cache tags from a hook:

```python
@authors.on("after_update")
async def invalidate_posts_cache(author, ctx):
    # Manually fire invalidation for posts when an author changes
    await app.hooks.fire("cache:invalidate", {"tag": "posts"}, ctx)
```

This pattern is only needed for denormalised or embedded data.

## Inspecting the cache

For debugging, connect to Redis directly and list keys:

```bash
redis-cli --scan --pattern "cinder:*"
```

Clear all Cinder cache entries:

```bash
redis-cli --scan --pattern "cinder:*" | xargs redis-cli del
```
