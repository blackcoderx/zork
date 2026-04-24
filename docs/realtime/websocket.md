# WebSocket Guide

WebSocket provides bidirectional, persistent communication between clients and the server. Use it when you need real-time interactivity or client-to-server messaging.

## Connection

### Basic Connection

```javascript
const ws = new WebSocket("ws://localhost:8000/api/realtime");

ws.onopen = () => {
  console.log("Connected");
};

ws.onclose = () => {
  console.log("Disconnected");
};
```

### With Authentication

Pass a JWT token as a query parameter:

```javascript
const token = getAuthToken();
const ws = new WebSocket(`ws://localhost:8000/api/realtime?token=${token}`);
```

### Production (Always Use TLS)

```javascript
// Always use wss:// in production
const ws = new WebSocket("wss://api.example.com/api/realtime?token=" + token);
```

## Protocol

### Message Format

All messages are JSON strings:

```javascript
// Outgoing (client to server)
{ "action": "subscribe", "channel": "..." }

// Incoming (server to client)
{ "type": "ack", "action": "subscribe", "channel": "..." }
```

### Response Types

| Type | Description |
|------|-------------|
| `ack` | Action acknowledged successfully |
| `error` | Action failed with an error message |
| `pong` | Response to ping (keepalive) |
| `ping` | Server-initiated keepalive ping |
| `envelope` | Realtime event envelope |

## Actions

### Subscribe

Subscribe to a channel to receive events:

```javascript
ws.send(JSON.stringify({
  action: "subscribe",
  channel: "collection:posts"
}));
```

Response:

```json
{ "type": "ack", "action": "subscribe", "channel": "collection:posts" }
```

### Unsubscribe

Stop receiving events for a channel:

```javascript
ws.send(JSON.stringify({
  action: "unsubscribe",
  channel: "collection:posts"
}));
```

Response:

```json
{ "type": "ack", "action": "unsubscribe", "channel": "collection:posts" }
```

### Authenticate Mid-Session

If you connected without a token, you can authenticate later:

```javascript
ws.send(JSON.stringify({
  action: "auth",
  token: "your-jwt-token"
}));
```

Response:

```json
{ "type": "ack", "action": "auth" }
```

### Ping

Send a ping to check the connection:

```javascript
ws.send(JSON.stringify({
  action: "ping"
}));
```

Response:

```json
{ "type": "pong" }
```

## Channel Types

### Collection Channels

Subscribe to collection events:

```javascript
// All events for a collection
ws.send(JSON.stringify({
  action: "subscribe",
  channel: "collection:posts"
}));

// Custom channel for specific use cases
ws.send(JSON.stringify({
  action: "subscribe",
  channel: "fraud:detected"
}));
```

### Error Responses

Invalid channels are rejected:

```json
{ "type": "error", "message": "Invalid channel name format" }
```

Channel names must be alphanumeric with colons, underscores, hyphens, and dots. Maximum length is 256 characters.

## Receiving Events

When an event occurs, you'll receive an envelope:

```javascript
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === "envelope") {
    console.log(`Event: ${data.event}`);
    console.log(`Collection: ${data.collection}`);
    console.log(`Record:`, data.record);
    
    // Handle different event types
    switch (data.event) {
      case "create":
        handleCreate(data.record);
        break;
      case "update":
        handleUpdate(data.record, data.previous);
        break;
      case "delete":
        handleDelete(data.record);
        break;
    }
  }
};
```

## Complete Example

```javascript
class RealtimeClient {
  constructor(url, token = null) {
    this.url = token ? `${url}?token=${token}` : url;
    this.ws = null;
    this.handlers = new Map();
  }

  connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);
      
      this.ws.onopen = () => {
        console.log("Connected");
        resolve();
      };
      
      this.ws.onerror = (error) => {
        console.error("Error:", error);
        reject(error);
      };
      
      this.ws.onclose = () => {
        console.log("Disconnected");
      };
      
      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        this.handleMessage(data);
      };
    });
  }

  handleMessage(data) {
    if (data.type === "envelope") {
      const handlers = this.handlers.get(data.channel) || [];
      handlers.forEach(handler => handler(data));
    }
  }

  subscribe(channel, handler) {
    const existing = this.handlers.get(channel) || [];
    this.handlers.set(channel, [...existing, handler]);
    
    this.ws.send(JSON.stringify({
      action: "subscribe",
      channel: channel
    }));
  }

  unsubscribe(channel) {
    this.handlers.delete(channel);
    this.ws.send(JSON.stringify({
      action: "unsubscribe",
      channel: channel
    }));
  }

  authenticate(token) {
    this.ws.send(JSON.stringify({
      action: "auth",
      token: token
    }));
  }
}

// Usage
const client = new RealtimeClient(
  "wss://api.example.com/api/realtime",
  authToken
);

await client.connect();

// Listen for new posts
client.subscribe("collection:posts", (event) => {
  if (event.event === "create") {
    addPostToFeed(event.record);
  }
});
```

## Python Client Example

Using the `websockets` library:

```python
import asyncio
import websockets
import json

async def main():
    uri = "ws://localhost:8000/api/realtime"
    
    async with websockets.connect(uri) as ws:
        # Subscribe to posts
        await ws.send(json.dumps({
            "action": "subscribe",
            "channel": "collection:posts"
        }))
        
        # Receive acknowledgments and events
        async for message in ws:
            data = json.loads(message)
            print(f"Received: {data}")
            
            if data.get("type") == "envelope":
                print(f"Event: {data['event']}")
                print(f"Record: {data['record']}")

asyncio.run(main())
```

## Error Handling

### Connection Errors

```javascript
ws.onerror = (error) => {
  console.error("WebSocket error:", error);
  // Attempt reconnection
  setTimeout(() => connect(), 5000);
};

ws.onclose = (event) => {
  if (event.code !== 1000) {
    console.log("Connection lost, reconnecting...");
    setTimeout(() => connect(), 5000);
  }
};
```

### Authentication Errors

```javascript
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === "error") {
    if (data.message.includes("Invalid")) {
      // Token invalid, re-authenticate
      refreshToken().then(token => {
        client.authenticate(token);
      });
    }
  }
};
```

## Security

### Origin Validation

Enable Origin header validation to prevent Cross-Site WebSocket Hijacking:

```python
app.realtime.configure_origin_check(
    enabled=True,
    origin_regex=r"https://.*\.yourapp\.com",
)
```

Connections from origins not matching the regex will be rejected with code 1008. Origin check is disabled by default for backward compatibility.

### Token Security

- Use short-lived tokens (15 minutes or less)
- Always use `wss://` in production
- Tokens appear in server logs when passed via query parameter

## Next Steps

- [SSE Guide](/realtime/sse) — Server-Sent Events for simpler use cases
- [Redis Broker](/realtime/redis-broker) — Scale to multiple processes