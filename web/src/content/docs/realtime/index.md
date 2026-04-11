---
title: Realtime
description: Live updates via WebSocket and Server-Sent Events
sidebar:
  order: 1
---

Cinder broadcasts every create, update, and delete operation to connected clients in real time. No additional setup is needed — realtime is enabled by default.

## Endpoints

| Protocol | URL | Authentication |
|----------|-----|----------------|
| WebSocket | `ws://host/api/realtime` | Token in first message |
| SSE | `GET /api/realtime/sse` | Token as query param |

## Quick start

**WebSocket (JavaScript):**

```javascript
const ws = new WebSocket("ws://localhost:8000/api/realtime");

ws.onopen = () => {
  // Authenticate
  ws.send(JSON.stringify({ action: "auth", token: "eyJ..." }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === "ack" && msg.action === "auth") {
    // Subscribe to a channel after authenticating
    ws.send(JSON.stringify({ action: "subscribe", channel: "collection:posts" }));
  }

  if (msg.type === "envelope") {
    console.log(msg.event, msg.collection, msg.record);
    // e.g. "create" "posts" { id: "...", title: "..." }
  }
};
```

**SSE (JavaScript):**

`channel` is required. Subscribe to one or more channels as query parameters:

```javascript
const source = new EventSource(
  "http://localhost:8000/api/realtime/sse?token=eyJ...&channel=collection:posts"
);

source.addEventListener("create", (event) => {
  const envelope = JSON.parse(event.data);
  console.log("New record:", envelope.record);
});
```

## Event format

```json
{
  "channel": "collection:posts",
  "event": "create",
  "collection": "posts",
  "record": {
    "id": "...",
    "title": "New Post",
    "created_at": "..."
  },
  "id": "...",
  "ts": "2024-01-01T00:00:00+00:00"
}
```

The `event` field is one of `create`, `update`, or `delete`. For `update` and `delete`, a `previous` key contains the record's prior state.

## Access control

Events are filtered per-client based on the collection's access control rules:

- `read:public` — broadcast to all clients (authenticated or not)
- `read:authenticated` — only clients that have authenticated
- `read:owner` — only the client who owns the record
- `read:admin` — only admin clients

## Scaling

The default broker runs in-process and only works with a single server process. For multi-process or multi-server deployments, switch to the Redis broker:

```python
app.configure_redis(url="redis://localhost:6379")
```

See the [Redis Broker](/realtime/redis/) page for details.

## Advanced: `app.realtime` API

The `app.realtime` object exposes several methods for customising the realtime layer. All must be called **before** `app.build()` or `app.serve()`.

### Publishing custom events

Send an arbitrary event to any channel from a hook, background task, or anywhere in your code:

```python
@orders.on("after_create")
async def notify(order, ctx):
    await app.realtime.publish("order:new", {"order_id": order["id"]})
```

Custom channel names are accepted. Clients subscribed to that channel receive the event.

### Disabling auto-emit for a collection

By default, every CRUD operation on every collection is broadcast. To opt out for a specific collection (e.g. high-frequency audit logs):

```python
app.realtime.disable_auto_emit("audit_logs")
app.realtime.enable_auto_emit("audit_logs")  # re-enable
```

### Disabling all auto-emit

```python
app.realtime.enabled = False  # no CRUD events are broadcast at all
```

### Custom envelope shape

Override the envelope builder to change the structure of every broadcast event:

```python
def my_envelope(collection, event, record, *, previous=None):
    return {
        "channel": f"collection:{collection}",
        "event": event,
        "collection": collection,
        "record": record,
        "previous": previous,
        "id": record.get("id"),
        "ts": "...",
        # add your own fields here
        "app_version": "2.0",
    }

app.realtime.envelope_builder = my_envelope
```

### Custom WebSocket routes

Register additional WebSocket routes alongside the built-in `/api/realtime`:

```python
async def my_chat_handler(websocket):
    await websocket.accept()
    # custom protocol ...

app.realtime.add_websocket_route("/api/chat", my_chat_handler)
```

## In this section

- [WebSocket](/realtime/websocket/) — full WebSocket protocol reference
- [Server-Sent Events](/realtime/sse/) — SSE connection and event format
- [Redis Broker](/realtime/redis/) — scaling realtime with Redis
