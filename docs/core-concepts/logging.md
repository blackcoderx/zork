# Logging

Zork uses [structlog](https://www.structlog.org/) for structured logging, providing a clean and configurable logging experience out of the box. Logs are automatically configured when you build or serve your application.

## Quick Start

Zork comes ready to use with sensible defaults:

```python
from zork import Zork

app = Zork(database="app.db")
app.serve()
```

That's it! Logs are automatically configured with:
- **Level**: INFO
- **Format**: Console (human-readable)
- **Colors**: Auto-detected based on terminal

## Configuration

### Environment Variables

Control logging behavior via environment variables:

| Variable | Default | Options | Description |
|----------|---------|---------|-------------|
| `ZORK_LOG_LEVEL` | INFO | DEBUG, INFO, WARNING, ERROR, CRITICAL | Minimum log level |
| `ZORK_LOG_FORMAT` | console | console, json | Output format |
| `ZORK_LOG_COLORIZE` | auto | auto, true, false | Enable ANSI colors |
| `ZORK_LOG_INCLUDE_TIMESTAMP` | true | true, false | Include ISO timestamp |
| `ZORK_LOG_INCLUDE_MODULE` | true | true, false | Include logger name |

### Development

```bash
# Development: verbose, colored output
ZORK_LOG_LEVEL=DEBUG ZORK_LOG_COLORIZE=true python main.py
```

### Production

```bash
# Production: JSON output for log aggregation
ZORK_LOG_FORMAT=json ZORK_LOG_LEVEL=INFO python main.py
```

JSON output is compatible with log aggregation systems like:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Datadog
- CloudWatch Logs
- Grafana Loki

### Programmatic Setup

For full control, configure logging programmatically:

```python
from zork.logging import setup, get_logger

# Configure with custom settings
setup(level="DEBUG", format="console", colorize=True)

# Get a logger for your module
log = get_logger("myapp")
log.info("server_started", port=8000)
```

## Using Loggers

### Basic Usage

```python
from zork.logging import get_logger

log = get_logger("myapp")

log.debug("debug_message", key="value")
log.info("info_message", user_id=123)
log.warning("warning_message", remaining_tries=1)
log.error("error_message", error="connection_failed")
log.critical("critical_message", system="unstable")
```

### Contextual Logging

Bind request-level context that automatically appears in all log entries:

```python
from zork.logging import bind_context, reset_context

# Bind context (e.g., at request start)
bind_context(request_id="abc123", user_id=42)

# All subsequent logs include this context
log.info("processing_request")  # Includes request_id and user_id

# Clear context (e.g., at request end)
reset_context()
```

This is particularly useful in hooks and middleware:

```python
@app.on("app:startup")
async def on_startup(ctx):
    log = get_logger("zork")
    log.info("application_started", version="1.0.0")
```

## Structured Logging

Structured logging separates context from messages, making logs easy to search and analyze:

```python
log.info(
    "user_action",
    user_id=123,
    action="purchase",
    amount=99.99,
    currency="USD"
)
```

### Console Output

```
2024-01-15T10:30:00.123Z | INFO  | myapp | user_action | user_id=123 action=purchase amount=99.99
```

### JSON Output

```json
{"event": "user_action", "user_id": 123, "action": "purchase", "amount": 99.99, "currency": "USD", "level": "info", "timestamp": "2024-01-15T10:30:00.123Z"}
```

## Integration with Uvicorn

Zork automatically suppresses uvicorn's access logs to reduce noise:

```python
# These are automatically set to WARNING:
# - uvicorn
# - uvicorn.access
# - uvicorn.error
```

To enable uvicorn logging for debugging:

```python
import logging
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
```

## Best Practices

### Log Levels

- **DEBUG**: Detailed diagnostic information (disabled in production)
- **INFO**: Normal operational events
- **WARNING**: Unexpected but handled events
- **ERROR**: Serious problems that prevented operation
- **CRITICAL**: System is unusable

### What to Log

```python
# Good: Structured with context
log.info("request_completed", method="GET", path="/api/users", duration_ms=45)

# Good: External calls with duration
log.info("database_query", table="users", rows_returned=10, duration_ms=5)

# Bad: Plain text without structure
log.info("User fetched")
```

### What NOT to Log

```python
# Never log sensitive data
log.info("user_login", password=password)           # BAD
log.info("user_login", token=token)                 # BAD

# Log safe identifiers instead
log.info("user_login", user_id=user.id)             # GOOD
log.info("request_failed", request_id=request_id)  # GOOD
```

## Log Aggregation

For production deployments with multiple instances, aggregate logs to a central system:

### JSON Format Example

With `ZORK_LOG_FORMAT=json`, each log line is a valid JSON object:

```json
{"level": "info", "timestamp": "2024-01-15T10:30:00.123Z", "event": "request_completed", "method": "GET", "path": "/api/users", "status": 200}
{"level": "error", "timestamp": "2024-01-15T10:30:01.456Z", "event": "database_error", "error": "connection_timeout", "instance": "server-1"}
```

This format integrates easily with:
- Elasticsearch + Kibana
- Grafana Loki
- Datadog
- AWS CloudWatch Logs
- Google Cloud Logging

## Next Steps

- [Lifecycle Hooks](/core-concepts/lifecycle-hooks) — Trigger actions on events
- [Error Handling](/core-concepts/errors) — Structured error responses
- [Environment Variables](/deployment/environment-variables) — All configuration options