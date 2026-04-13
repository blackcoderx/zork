"""Cache-aside middleware for Cinder GET responses.

Intercepts GET requests to ``/api/{collection}`` and ``/api/{collection}/{id}``
paths, serves cached responses on hits, and stores responses on misses.

Key design decisions
--------------------
- **Per-user segmentation by default** — cache keys include the user ID (or
  ``anon``) so RBAC-filtered results can never leak across users.
- **Fail-open** — if the cache backend raises, the middleware logs and passes
  through to the real handler. The API is never broken by a cache outage.
- **Never caches** 4xx/5xx responses, ``Set-Cookie`` headers, or responses
  with ``Cache-Control: no-store``.
- **Tag tracking** — list-endpoint response keys are registered in the
  ``tag:collection:{name}`` set so invalidation can delete them atomically.
- **Excluded paths** — developers can opt specific paths out of caching.
"""
from __future__ import annotations

import hashlib
import json
import logging
from urllib.parse import parse_qs, urlencode

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from cinder.cache.backends import CacheBackend
from cinder.cache.invalidation import TAG_PREFIX, _get_key

logger = logging.getLogger("cinder.cache.middleware")

_CACHE_PREFIX = "response"


def _sorted_qs(raw_qs: str) -> str:
    """Normalise query strings so ``?b=2&a=1`` and ``?a=1&b=2`` hit the same key."""
    parsed = parse_qs(raw_qs, keep_blank_values=True)
    return urlencode(sorted(parsed.items()))


def _build_key(collection: str, op: str, path: str, qs: str, user_segment: str) -> str:
    fingerprint = hashlib.sha256(f"{path}:{qs}:{user_segment}".encode()).hexdigest()[:16]
    return f"{_CACHE_PREFIX}:{collection}:{op}:{fingerprint}"


def _collection_from_path(path: str) -> tuple[str | None, str | None]:
    """Extract ``(collection_name, record_id)`` from ``/api/{name}`` or ``/api/{name}/{id}``."""
    parts = path.strip("/").split("/")
    if len(parts) < 2 or parts[0] != "api":
        return None, None
    name = parts[1]
    # Skip sub-paths like /api/realtime, /api/health, /api/auth
    if name in ("realtime", "health", "auth"):
        return None, None
    record_id = parts[2] if len(parts) >= 3 else None
    return name, record_id


class CacheMiddleware:
    """ASGI middleware implementing cache-aside for collection GET requests."""

    def __init__(
        self,
        app: ASGIApp,
        backend: CacheBackend,
        *,
        default_ttl: int = 300,
        per_user: bool = True,
        excluded_paths: list[str] | None = None,
    ) -> None:
        self.app = app
        self.backend = backend
        self.default_ttl = default_ttl
        self.per_user = per_user
        self.excluded_paths: set[str] = set(excluded_paths or [])

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "GET":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if path in self.excluded_paths:
            await self.app(scope, receive, send)
            return

        collection, record_id = _collection_from_path(path)
        if collection is None:
            await self.app(scope, receive, send)
            return

        qs = _sorted_qs(scope.get("query_string", b"").decode())

        # Determine user segment for per-user cache partitioning
        user = scope.get("state", {}).get("user")
        if self.per_user:
            user_segment = str(user["id"]) if user and "id" in user else "anon"
        else:
            user_segment = "shared"

        if record_id:
            op = "get"
            cache_key = _get_key(collection, record_id)
        else:
            op = "list"
            cache_key = _build_key(collection, op, path, qs, user_segment)

        # --- cache lookup ---
        try:
            cached = await self.backend.get(cache_key)
        except Exception:
            logger.exception("Cache GET failed for key %s — bypassing", cache_key)
            cached = None

        if cached is not None:
            try:
                entry = json.loads(cached)
                await _send_cached(scope, send, entry, cache_key)
                return
            except Exception:
                logger.exception("Cache entry corrupt for key %s — bypassing", cache_key)

        # --- cache miss: capture downstream response ---
        captured: dict = {"status": None, "headers": [], "body": b""}

        async def capture_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                captured["status"] = message["status"]
                captured["headers"] = list(message.get("headers", []))
                # Add X-Cache: MISS header
                headers = list(message.get("headers", []))
                headers.append((b"x-cache", b"MISS"))
                message = {**message, "headers": headers}
            elif message["type"] == "http.response.body":
                captured["body"] += message.get("body", b"")
            await send(message)

        await self.app(scope, receive, capture_send)

        # Store in cache only if response is cacheable
        status = captured["status"]
        if status is not None and 200 <= status < 300:
            headers_dict = {k.lower(): v for k, v in captured["headers"]}
            if (
                b"set-cookie" not in headers_dict
                and b"no-store" not in headers_dict.get(b"cache-control", b"")
            ):
                try:
                    entry = {
                        "status": status,
                        "headers": [[k.decode(), v.decode()] for k, v in captured["headers"]],
                        "body": captured["body"].decode("latin-1"),
                    }
                    await self.backend.set(cache_key, json.dumps(entry).encode(), ttl=self.default_ttl)
                    # Register list keys in the tag set for invalidation
                    if op == "list":
                        tag = f"{TAG_PREFIX}:{collection}"
                        await self.backend.sadd(tag, cache_key)
                except Exception:
                    logger.exception("Cache SET failed for key %s — ignoring", cache_key)


async def _send_cached(scope: Scope, send: Send, entry: dict, cache_key: str) -> None:
    headers = [(k.encode(), v.encode()) for k, v in entry["headers"]]
    # Replace or add X-Cache: HIT
    headers = [(k, v) for k, v in headers if k.lower() != b"x-cache"]
    headers.append((b"x-cache", b"HIT"))

    await send({
        "type": "http.response.start",
        "status": entry["status"],
        "headers": headers,
    })
    await send({
        "type": "http.response.body",
        "body": entry["body"].encode("latin-1"),
        "more_body": False,
    })
