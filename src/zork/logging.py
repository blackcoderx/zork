from __future__ import annotations

import logging
import os
import sys
from typing import Any, Literal

import structlog
from structlog.processors import TimeStamper, add_log_level
from structlog.stdlib import LoggerFactory


def setup(
    level: str = "INFO",
    format: Literal["console", "json"] = "console",
    colorize: Literal["auto", "true", "false"] = "auto",
    include_timestamp: bool = True,
    include_module: bool = True,
) -> None:
    """Configure structlog for Zork.

    Args:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Output format - "console" for human-readable, "json" for production
        colorize: Enable ANSI colors in console output (auto detects terminal)
        include_timestamp: Include ISO timestamp in output
        include_module: Include logger name in output
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
    ]

    if include_timestamp:
        processors.append(TimeStamper(fmt="iso", utc=True))

    if format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        _colorize = _should_colorize() if colorize == "auto" else colorize == "true"
        processors.append(
            structlog.dev.ConsoleRenderer(
                colors=_colorize,
                force_colors=_colorize,
            )
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configure_stdlib_logging(log_level, format)


def configure_from_env() -> None:
    """Configure logging from environment variables.

    Environment variables:
        ZORK_LOG_LEVEL: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
        ZORK_LOG_FORMAT: console, json (default: console)
        ZORK_LOG_COLORIZE: auto, true, false (default: auto)
        ZORK_LOG_INCLUDE_TIMESTAMP: true, false (default: true)
        ZORK_LOG_INCLUDE_MODULE: true, false (default: true)
    """
    setup(
        level=env("ZORK_LOG_LEVEL", "INFO"),
        format=env("ZORK_LOG_FORMAT", "console"),
        colorize=env("ZORK_LOG_COLORIZE", "auto"),
        include_timestamp=env_bool("ZORK_LOG_INCLUDE_TIMESTAMP", True),
        include_module=env_bool("ZORK_LOG_INCLUDE_MODULE", True),
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a structlog logger instance.

    Args:
        name: Logger name. If None, uses "zork" as default.

    Returns:
        A structlog bound logger.

    Example:
        >>> log = get_logger("myapp")
        >>> log.info("user_action", user_id=123, action="login")
    """
    if name:
        return structlog.get_logger(name)
    return structlog.get_logger("zork")


def _should_colorize() -> bool:
    """Check if terminal supports ANSI colors."""
    if not hasattr(sys.stdout, "isatty"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.getenv("TERM") == "dumb":
        return False
    return True


def _configure_stdlib_logging(level: int, format: str) -> None:
    """Configure standard library logging to work with structlog."""
    root = logging.getLogger("zork")
    root.setLevel(level)

    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        if format == "json":
            handler.setFormatter(JsonFormatter())
        else:
            handler.setFormatter(StdlibFormatter())
        root.addHandler(handler)


def env(key: str, default: str) -> str:
    return os.getenv(key, default)


def env_bool(key: str, default: bool) -> bool:
    val = os.getenv(key, "").lower()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    return default


class StdlibFormatter(logging.Formatter):
    """Formatter for stdlib logging that outputs in structlog-like format."""

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return msg


class JsonFormatter(logging.Formatter):
    """JSON formatter for stdlib logging."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_obj = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def bind_context(**kwargs: Any) -> None:
    """Bind contextual information to all log entries.

    Useful for request-level data like request_id, user_id, etc.

    Args:
        **kwargs: Context variables to bind.

    Example:
        >>> bind_context(request_id="abc123", user_id=42)
        >>> log.info("request processed")  # Includes request_id and user_id
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(**kwargs)


def reset_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()