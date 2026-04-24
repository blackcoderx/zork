# Redis Broker Configuration

The Redis broker enables realtime event distribution across multiple processes or server instances. Use it when scaling beyond a single process or running in a distributed environment.

## Overview

When using the in-process broker (default), events are only delivered to clients connected to the same process. The Redis broker uses Redis pub/sub to fan out events to all connected clients regardless of which process they're connected to.

**Architecture:**

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Process A  │     │  Process B  │     │  Process C  │
│  ┌───────┐  │     │  ┌───────┐  │     │  ┌───────┐  │
│  │Client │  │     │  │Client │  │     │  │Client │  │
│  └───┬───┘  │     │  └───┬───┘  │     │  └───┬───┘  │
│      │      │     │      │      │     │      │      │
│      ▼      │     │      ▼      │     │      ▼      │
│  ┌───────┐  │     │  ┌───────┐  │     │  ┌───────┐  │
│  │Broker │  │     │  │Broker │  │     │  │Broker │  │
│  └───┬───┘  │     │  └───┬───┘  │     │  └───┬───┘  │
└──────┼──────┘     └──────┼──────┘     └──────┼──────┘
       │                        │               │
       └────────────────────────┼───────────────┘
                               ▼
                    ┌─────────────────────┐
                    │       Redis         │
                    │  (pub/sub channel)  │
                    └───��─────────────────┘
```

## Setup

### Basic Setup

Configure Redis for all Zork subsystems:

```python
app.configure_redis(url="redis://localhost:6379/0")
```

### Custom Broker Configuration

For full control over reconnection behavior:

```python
from zork.realtime import RedisBroker

app.realtime.use_broker(
    RedisBroker(
        queue_size=100,
        max_retries=3,
        retry_base_delay=1.0,
        retry_max_delay=30.0,
    )
)
```

## Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_retries` | `int` | `0` | Max reconnection attempts. `0` = fail-fast (no retry). Higher values enable retries. |
| `retry_base_delay` | `float` | `1.0` | Initial backoff delay in seconds |
| `retry_max_delay` | `float` | `30.0` | Maximum backoff delay cap in seconds |
| `queue_size` | `int` | `100` | Per-subscription queue size |

## Reconnection Strategies

### Fail-Fast Mode (Default)

The default `max_retries=0` logs a warning and does not retry on connection failure:

```python
app.realtime.use_broker(RedisBroker())  # max_retries=0 by default
```

**Use when:**
- You want to detect connection issues immediately
- You have alternative fallback behavior
- Debugging connection issues

### Resilient Mode

For production environments where Redis availability is critical:

```python
app.realtime.use_broker(
    RedisBroker(
        max_retries=5,  # Retry up to 5 times
        retry_base_delay=1.0,  # Start with 1 second
        retry_max_delay=30.0,  # Cap at 30 seconds
    )
)
```

**Use when:**
- Redis availability is critical
- You want automatic recovery after temporary outages
- Running in a containerized environment with restart policies

## Backoff Calculation

The backoff delay follows exponential growth:

```
delay = min(retry_base_delay * (2 ^ (attempt - 1)), retry_max_delay)
```

**Example with default retry settings (base=1.0, max=30.0):**

| Attempt | Delay |
|---------|-------|
| 1 | 1.0s |
| 2 | 2.0s |
| 3 | 4.0s |
| 4 | 8.0s |
| 5 | 16.0s |
| 6 | 30.0s (capped) |
| 7+ | 30.0s (capped) |

## Logging

The broker logs important events:

```
WARNING: RedisBroker: max_retries=0 (fail-fast mode).
WARNING: Redis broker: connection lost (attempt 1/3), reconnecting in 1.0s
ERROR: Redis broker: exceeded max retries (3) on channels ['collection:posts']
```

## Production Checklist

Before deploying with Redis broker:

- [ ] Test reconnection behavior by stopping/starting Redis
- [ ] Set appropriate `max_retries` for your reliability requirements
- [ ] Configure monitoring for `failed_count`
- [ ] Set up Redis connection pooling
- [ ] Test with multiple server processes

## Troubleshooting

### Events Stop Arriving

**Possible causes:**
1. Redis connection lost
2. Subscription not properly re-established

**Solutions:**
```python
# Check failed_count
print(f"Failed operations: {app.realtime.broker.failed_count}")

# Check subscription count
print(f"Active subscriptions: {app.realtime.broker.subscription_count}")
```

### Never Reconnects

**Cause:** `max_retries=0` set

**Solution:**
```python
# Set to None for infinite retries
app.realtime.use_broker(RedisBroker(max_retries=None))
```

### Long Delays Before Reconnect

**Cause:** Backoff too aggressive

**Solution:**
```python
# Lower the base and max
app.realtime.use_broker(
    RedisBroker(
        retry_backoff_base=0.5,
        retry_backoff_max=10.0,
    )
)
```

### Redis Connection Error

**Check:**
1. Redis is running: `redis-cli ping`
2. URL is correct
3. Network connectivity
4. Redis `maxmemory` not exceeded

## Multi-Process Example

### With Gunicorn

```bash
# Start 4 worker processes
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

All processes share events via Redis:

```python
# main.py
from zork import Zork, Collection, TextField
from zork.realtime import RedisBroker

app = Zork(database="app.db")

posts = Collection("posts", fields=[
    TextField("title", required=True),
])

app.register(posts)

# Use Redis broker for multi-process support
app.realtime.use_broker(RedisBroker())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app.build(), host="0.0.0.0", port=8000)
```

### With Docker Compose

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ZORK_REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
```

## Comparison

| Feature | In-Process Broker | Redis Broker |
|---------|------------------|--------------|
| Multi-process | No | Yes |
| Connection required | No | Yes |
| Reconnection | N/A | Configurable |
| Complexity | Low | Medium |
| Dependencies | None | Redis |

## Next Steps

- [Realtime Overview](/realtime/overview) — Complete realtime documentation
- [WebSocket Guide](/realtime/websocket) — WebSocket usage
- [SSE Guide](/realtime/sse) — SSE usage