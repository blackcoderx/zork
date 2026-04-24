# Server-Sent Events Guide

Server-Sent Events (SSE) provides one-way server-to-client streaming over HTTP. Use SSE when you only need server-initiated updates and want simpler implementation than WebSocket.

## When to Use SSE

**Choose SSE when:**
- You only need server-to-client updates (notifications, feeds, progress)
- You want simpler client code (native EventSource API)
- You need automatic reconnection and resume (built-in)
- Your use case works through proxies and load balancers

**Choose WebSocket when:**
- You need bidirectional communication
- You have high-frequency message exchange
- You need client-to-server messaging

## Connection

### Basic Connection

```javascript
const eventSource = new EventSource(
  "http://localhost:8000/api/realtime/sse?channel=collection:posts"
);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log("Event:", data);
};
```

### With Authentication

Pass the JWT token via query parameter:

```javascript
const eventSource = new EventSource(
  `http://localhost:8000/api/realtime/sse?token=${token}&channel=collection:posts`
);
```

### Production (Always Use TLS)

```javascript
const eventSource = new EventSource(
  `https://api.example.com/api/realtime/sse?token=${token}&channel=collection:posts`
);
```

## Subscribing to Channels

Pass channels as query parameters. Each channel parameter adds a subscription:

```
GET /api/realtime/sse?channel=collection:posts&channel=collection:comments&channel=fraud:detected
```

Or in JavaScript:

```javascript
const channels = [
  "collection:posts",
  "collection:comments",
  "fraud:detected"
].map(c => `channel=${encodeURIComponent(c)}`).join("&");

const url = `http://localhost:8000/api/realtime/sse?${channels}`;
const eventSource = new EventSource(url);
```

## Event Format

SSE uses the standard `text/event-stream` format:

```
event: create
data: {"type":"envelope","channel":"collection:posts","event":"create","collection":"posts","record":{"id":"abc","title":"Hello"},"id":"abc","ts":"2024-01-15T10:30:00Z"}
id: abc

event: update
data: {"type":"envelope","channel":"collection:posts","event":"update","record":{"id":"abc","title":"Updated"},"id":"abc","ts":"2024-01-15T10:35:00Z"}
id: abc

: ping
```

## Event Types

Events are typed by the `event` field in the envelope:

```javascript
const eventSource = new EventSource(
  "http://localhost:8000/api/realtime/sse?channel=collection:posts"
);

// Listen for specific event types
eventSource.addEventListener("create", (event) => {
  const data = JSON.parse(event.data);
  console.log("New record:", data.record);
});

eventSource.addEventListener("update", (event) => {
  const data = JSON.parse(event.data);
  console.log("Updated record:", data.record);
});

eventSource.addEventListener("delete", (event) => {
  const data = JSON.parse(event.data);
  console.log("Deleted record:", data.record);
});

// Or use the default message handler
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // Handle all events here
};
```

## Complete Example

```javascript
class SSEClient {
  constructor(url) {
    this.url = url;
    this.eventSource = null;
    this.handlers = {
      create: [],
      update: [],
      delete: [],
      message: []
    };
  }

  connect(channels = []) {
    const channelParams = channels
      .map(c => `channel=${encodeURIComponent(c)}`)
      .join("&");
    const url = this.url + (channelParams ? `?${channelParams}` : "");
    
    this.eventSource = new EventSource(url);
    
    // Set up event listeners
    ["create", "update", "delete"].forEach(eventType => {
      this.eventSource.addEventListener(eventType, (event) => {
        const data = JSON.parse(event.data);
        this.handlers[eventType].forEach(handler => handler(data));
      });
    });
    
    this.eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handlers.message.forEach(handler => handler(data));
    };
    
    this.eventSource.onerror = (error) => {
      console.error("SSE error:", error);
      // EventSource handles reconnection automatically
    };
  }

  on(eventType, handler) {
    if (this.handlers[eventType]) {
      this.handlers[eventType].push(handler);
    }
  }

  close() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}

// Usage
const client = new SSEClient("http://localhost:8000/api/realtime/sse");

client.on("create", (data) => {
  console.log("Created:", data.record);
});

client.on("update", (data) => {
  console.log("Updated:", data.record);
});

client.connect(["collection:posts", "collection:comments"]);
```

## Python Client Example

Using `aiohttp`:

```python
import asyncio
import aiohttp

async def sse_client():
    url = "http://localhost:8000/api/realtime/sse"
    params = {"channel": ["collection:posts", "collection:comments"]}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            async for line in response.content:
                line = line.decode().strip()
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    print(f"Event: {data.get('event')}")
                    print(f"Record: {data.get('record')}")

asyncio.run(sse_client())
```

Using `sseclient-py`:

```python
import sseclient
import requests

response = requests.get(
    "http://localhost:8000/api/realtime/sse",
    params={"channel": "collection:posts"},
    stream=True
)

client = sseclient.SSEClient(response)
for event in client.events():
    print(f"Event: {event.event}")
    print(f"Data: {event.data}")
```

## Reconnection

EventSource automatically handles reconnection:

1. When the connection drops, EventSource reconnects after a delay
2. It sends the `Last-Event-ID` header to resume from where it left off
3. Your server can track the last event ID per client

```javascript
let lastEventId = null;

// After receiving events
eventSource.onmessage = (event) => {
  lastEventId = event.lastEventId;
  const data = JSON.parse(event.data);
  // Process data
};

// On reconnect, Last-Event-ID is automatically sent
eventSource.onerror = (error) => {
  console.log("Connection lost, will reconnect automatically");
};
```

## CORS for SSE

### Browser Considerations

SSE is subject to CORS restrictions. If your page is served from a different origin than your API:

1. Configure CORS for realtime endpoints:

```python
app.realtime.configure_cors(
    allow_origins=["https://yourapp.com"],
    allow_credentials=True,
)
```

2. The browser may send a preflight `OPTIONS` request.

### Response Headers

When CORS is configured, SSE responses include appropriate headers:

```
Access-Control-Allow-Origin: https://yourapp.com
Vary: Origin
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

## Heartbeat

SSE includes periodic heartbeat comments to keep the connection alive through proxies:

```
: ping
```

These are ignored by the browser but prevent proxies from closing idle connections.

## Error Handling

### Connection Errors

```javascript
eventSource.onerror = (error) => {
  if (eventSource.readyState === EventSource.CONNECTING) {
    console.log("Reconnecting...");
  } else if (eventSource.readyState === EventSource.CLOSED) {
    console.log("Connection closed permanently");
  }
};
```

### HTTP Error Responses

If authentication fails, the server returns a JSON error:

```javascript
// Server returns: {"status": 401, "error": "Invalid request"}
// As a text/event-stream with an error type
```

Handle this by checking the response:

```javascript
const eventSource = new EventSource(url);

// Listen for error events if your server sends them
eventSource.addEventListener("error", (event) => {
  // Custom error handling
});
```

## Security

### Token Security

- SSE tokens appear in URLs (logged by proxies and server logs)
- Use short-lived tokens (15 minutes or less)
- Consider token refresh for long-lived SSE connections

### CORS Configuration

By default, SSE allows all origins (`*`) for backward compatibility. Configure CORS to restrict access:

```python
# Restrict to specific origins
app.realtime.configure_cors(
    allow_origins=["https://yourapp.com"],
)

# Use regex for dynamic origin matching
app.realtime.configure_cors(
    allow_origins=["https://app.example.com", "https://staging.example.com"],
    allow_origin_regex=r"https://.*\.yourapp\.com",
)
```

When `allow_origins` is not `*`, requests from origins not in the allowlist will be rejected with a 403 error.

## Next Steps

- [WebSocket Guide](/realtime/websocket) — Bidirectional communication
- [Redis Broker](/realtime/redis-broker) — Scale to multiple processes