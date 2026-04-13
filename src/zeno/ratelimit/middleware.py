"""Rate-limit middleware for Cinder.

Sits just above the cache middleware (rate-limit fires first so abusive traffic
never even reaches the cache lookup).

Default limits (configurable via env vars or programmatic API):
- Anonymous (no JWT): 100 requests / 60 seconds per IP
- Authenticated: 1000 requests / 60 seconds per user ID

Per-route rules can be added via ``RateLimitMiddleware.add_rule(...)``.

On limit exceeded, returns 429 with headers:
    X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset, Retry-After

Fail-open: if the backend raises, the middleware logs and passes through.
"""
from __future__ import annotations

import json
import logging
import math

from starlette.types import ASGIApp, Receive, Scope, Send

from cinder.ratelimit.backends import RateLimitBackend, RateLimitResult

logger = logging.getLogger("cinder.ratelimit.middleware")


class RateLimitRule:
    """A rate-limit rule for a specific path prefix and scope."""

    def __init__(
        self,
        path_prefix: str,
        *,
        limit: int,
        window: int,
        scope: str = "ip",  # "ip" | "user" | "both"
    ) -> None:
        self.path_prefix = path_prefix
        self.limit = limit
        self.window = window
        self.scope = scope


class RateLimitMiddleware:
    """ASGI middleware that enforces request rate limits."""

    def __init__(
        self,
        app: ASGIApp,
        backend: RateLimitBackend,
        *,
        anon_limit: int = 100,
        anon_window: int = 60,
        user_limit: int = 1000,
        user_window: int = 60,
        enabled: bool = True,
    ) -> None:
        self.app = app
        self.backend = backend
        self.anon_limit = anon_limit
        self.anon_window = anon_window
        self.user_limit = user_limit
        self.user_window = user_window
        self.enabled = enabled
        self._rules: list[RateLimitRule] = []

    def add_rule(self, rule: RateLimitRule) -> None:
        """Register a per-path rate-limit rule. Rules are checked before defaults."""
        self._rules.append(rule)

    def _find_rule(self, path: str) -> RateLimitRule | None:
        for rule in self._rules:
            if path.startswith(rule.path_prefix):
                return rule
        return None

    def _get_ip(self, scope: Scope) -> str:
        client = scope.get("client")
        if client:
            return client[0]
        # Check X-Forwarded-For via headers
        headers = dict(scope.get("headers", []))
        xff = headers.get(b"x-forwarded-for", b"").decode()
        if xff:
            return xff.split(",")[0].strip()
        return "unknown"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.enabled or scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        user = scope.get("state", {}).get("user")
        ip = self._get_ip(scope)

        rule = self._find_rule(path)

        if rule:
            limit, window = rule.limit, rule.window
            rl_scope = rule.scope
        else:
            if user:
                limit, window = self.user_limit, self.user_window
                rl_scope = "user"
            else:
                limit, window = self.anon_limit, self.anon_window
                rl_scope = "ip"

        # Build rate-limit key
        if rl_scope == "user" and user:
            rl_key = f"ratelimit:{path}:user:{user['id']}"
        elif rl_scope == "both":
            user_part = str(user["id"]) if user else ip
            rl_key = f"ratelimit:{path}:both:{user_part}"
        else:
            rl_key = f"ratelimit:{path}:ip:{ip}"

        try:
            result: RateLimitResult = await self.backend.check(rl_key, limit, window)
        except Exception:
            logger.exception("Rate-limit backend error — fail-open for %s", rl_key)
            await self.app(scope, receive, send)
            return

        retry_after = max(0, math.ceil(result.reset_at - __import__("time").time()))

        rl_headers = [
            (b"x-ratelimit-limit", str(limit).encode()),
            (b"x-ratelimit-remaining", str(result.remaining).encode()),
            (b"x-ratelimit-reset", str(int(result.reset_at)).encode()),
        ]

        if not result.allowed:
            rl_headers.append((b"retry-after", str(retry_after).encode()))
            body = json.dumps({"status": 429, "error": "Rate limit exceeded"}).encode()
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ] + rl_headers,
            })
            await send({"type": "http.response.body", "body": body, "more_body": False})
            return

        # Allowed — pass through and append rate-limit headers to the response
        async def send_with_rl_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", [])) + rl_headers
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_rl_headers)
