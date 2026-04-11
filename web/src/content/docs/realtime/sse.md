---
title: Server-Sent Events
description: Real-time updates over a standard HTTP SSE stream
sidebar:
  order: 3
---

Server-Sent Events (SSE) is a lightweight HTTP-based transport for receiving live updates. It is unidirectional (server → client) and proxy-friendly.

## Connecting

```
GET /api/realtime/sse?channel=collection:posts
```

**At least one `channel` parameter is required.** Without it you receive `400 Bad Request`.

Multiple channels:

```
GET /api/realtime/sse?channel=collection:posts&channel=collection:comments
```

With authentication:

```
GET /api/realtime/sse?token=eyJ...&channel=collection:posts
```

## Query parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `channel` | Yes (at least one) | Channel to subscribe to. Repeatable. |
| `token` | No | JWT token for authenticated collections. |

## Channel naming

Built-in collection channels follow the pattern `collection:{name}`:

- `collection:posts`
- `collection:users`

Access control is automatically applied for built-in collection channels based on the collection's `read` rule.

## Event format

Events arrive as SSE named events. The `event` field in the SSE frame matches the action (`create`, `update`, `delete`):

```
event: create
data: {"channel":"collection:posts","event":"create","collection":"posts","record":{"id":"...","title":"Hello"},"id":"...","ts":"..."}
id: abc123

event: update
data: {"channel":"collection:posts","event":"update","collection":"posts","record":{"id":"...","title":"Updated"},"previous":{"id":"...","title":"Old"},"id":"...","ts":"..."}
id: abc123
```

The `data` payload is the full envelope JSON:

| Field | Description |
|-------|-------------|
| `channel` | Channel name (e.g. `collection:posts`) |
| `event` | Action: `create`, `update`, or `delete` |
| `collection` | Collection name |
| `record` | The record in its current state |
| `previous` | Previous state (only on `update` and `delete`) |
| `id` | Record UUID |
| `ts` | ISO 8601 timestamp of the event |

## Heartbeat

The server sends a comment ping every 15 seconds to keep proxies from timing out the connection:

```
: ping
```

This is ignored by the browser's `EventSource` API.

## JavaScript example

```javascript
const source = new EventSource(
  "http://localhost:8000/api/realtime/sse?token=eyJ...&channel=collection:posts"
);

source.addEventListener("create", (event) => {
  const envelope = JSON.parse(event.data);
  console.log("New record:", envelope.record);
});

source.addEventListener("update", (event) => {
  const envelope = JSON.parse(event.data);
  console.log("Updated:", envelope.record, "was:", envelope.previous);
});

source.addEventListener("delete", (event) => {
  const envelope = JSON.parse(event.data);
  console.log("Deleted:", envelope.record.id);
});

source.onerror = () => console.error("SSE error");
```

## SSE vs WebSocket

| | SSE | WebSocket |
|---|-----|-----------|
| Protocol | HTTP | WS |
| Direction | Server → Client | Bidirectional |
| Subscribe at connect | Via query params | Via `subscribe` message |
| Auto-reconnect | Yes (browser built-in) | Manual |
| Proxy/firewall support | Excellent | Sometimes blocked |
| Auth | `?token=` query param | Query param or `auth` message |

Use SSE for dashboards and notification feeds. Use WebSocket if you need bidirectional communication or dynamic subscribe/unsubscribe after connecting.
