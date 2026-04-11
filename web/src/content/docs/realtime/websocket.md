---
title: WebSocket
description: Real-time updates over a persistent WebSocket connection
sidebar:
  order: 2
---

The WebSocket transport provides a persistent, bidirectional connection for receiving live events.

## Connecting

```
ws://localhost:8000/api/realtime
wss://yourapp.com/api/realtime   (TLS in production)
```

## Authentication

You can authenticate in two ways:

### Option 1 — Query parameter (at connect time)

```
ws://localhost:8000/api/realtime?token=eyJ...
```

The connection is rejected with close code `1008` if the token is invalid.

### Option 2 — Auth message (mid-session)

Send an `auth` action after connecting:

```json
{ "action": "auth", "token": "eyJ..." }
```

**Success response:**
```json
{ "type": "ack", "action": "auth" }
```

**Failure response:**
```json
{ "type": "error", "message": "Invalid token" }
```

Unauthenticated clients can still connect and will receive events for `read:public` collections.

## Subscribing to channels

After connecting (and optionally authenticating), subscribe to a channel:

```json
{ "action": "subscribe", "channel": "collection:posts" }
```

**Response:**
```json
{ "type": "ack", "action": "subscribe", "channel": "collection:posts" }
```

Subscribe to multiple collections by sending multiple subscribe messages.

## Unsubscribing

```json
{ "action": "unsubscribe", "channel": "collection:posts" }
```

**Response:**
```json
{ "type": "ack", "action": "unsubscribe", "channel": "collection:posts" }
```

## Ping / pong

Send a ping to check if the connection is alive:

```json
{ "action": "ping" }
```

**Response:**
```json
{ "type": "pong" }
```

The server also sends a `{ "type": "ping" }` frame every 30 seconds to keep the connection alive. No response is required from the client.

## Receiving events

Events arrive as JSON messages with `"type": "envelope"`:

```json
{
  "type": "envelope",
  "channel": "collection:posts",
  "event": "create",
  "collection": "posts",
  "record": {
    "id": "abc123",
    "title": "Hello World",
    "created_at": "2024-01-01T00:00:00+00:00"
  },
  "id": "abc123",
  "ts": "2024-01-01T00:00:00+00:00"
}
```

For `update` events, a `previous` key contains the record's state before the change:

```json
{
  "type": "envelope",
  "channel": "collection:posts",
  "event": "update",
  "collection": "posts",
  "record": { "id": "...", "title": "Updated Title", ... },
  "previous": { "id": "...", "title": "Old Title", ... },
  "id": "...",
  "ts": "..."
}
```

## Event types

| `event` value | Trigger |
|---------------|---------|
| `create` | A record was created (`POST`) |
| `update` | A record was updated (`PATCH`) |
| `delete` | A record was deleted (`DELETE`) |

## Channel naming

Built-in collection channels follow the pattern `collection:{name}`:

- `collection:posts`
- `collection:comments`

Access control is applied automatically for built-in collection channels. Custom channel names are also supported but receive no access filtering by default.

## Full JavaScript example

```javascript
const ws = new WebSocket("ws://localhost:8000/api/realtime");

ws.onopen = () => {
  // Authenticate
  ws.send(JSON.stringify({ action: "auth", token: "eyJ..." }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === "ack" && msg.action === "auth") {
    // Authenticated — now subscribe to channels
    ws.send(JSON.stringify({ action: "subscribe", channel: "collection:posts" }));
    return;
  }

  if (msg.type === "envelope") {
    console.log(msg.event, msg.collection, msg.record);
    // e.g. "create" "posts" { id: "...", title: "..." }
  }

  if (msg.type === "error") {
    console.error("Error:", msg.message);
  }
};

ws.onclose = () => console.log("Disconnected");
```
