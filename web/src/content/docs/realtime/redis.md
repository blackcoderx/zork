---
title: Redis Broker
description: Scale realtime to multiple server processes with Redis
sidebar:
  order: 4
---

The default realtime broker runs in-process. This works for single-process deployments but events do not cross process boundaries. If you run multiple Uvicorn workers or deploy across multiple servers, clients connected to different processes will miss events.

The Redis broker solves this by using Redis Pub/Sub as the shared message bus.

## Setup

Install the Redis extra:

```bash
pip install "cinder[redis]"
uv add "cinder[redis]"
```

Configure Redis:

```python
app.configure_redis(url="redis://localhost:6379")
```

Or via environment variable:

```dotenv
CINDER_REDIS_URL=redis://localhost:6379
```

When `CINDER_REDIS_URL` is set, Cinder automatically selects the Redis broker. All processes sharing the same Redis instance exchange events — every connected client receives updates regardless of which worker handled the write.

## Forcing a specific broker

```dotenv
CINDER_REALTIME_BROKER=redis    # always Redis
CINDER_REALTIME_BROKER=memory   # always in-process (even if Redis is configured)
```

## How it works

1. A CRUD operation fires on worker A
2. Worker A publishes the event to a Redis Pub/Sub channel
3. All workers (including A) receive the event from Redis
4. Each worker fans the event out to its locally connected WebSocket/SSE clients, filtered by access control

## Running multiple workers

```bash
gunicorn main:asgi_app -k uvicorn.workers.UvicornWorker -w 4
```

Or with uvicorn directly (not recommended for production — use gunicorn):

```bash
uvicorn main:asgi_app --workers 4
```

All workers must share the same `CINDER_REDIS_URL`.

## Redis connection

The Redis client is a shared singleton reused across caching, rate limiting, and realtime. A single `configure_redis()` call (or `CINDER_REDIS_URL`) configures all subsystems.
