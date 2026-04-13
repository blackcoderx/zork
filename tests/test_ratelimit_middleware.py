"""Tests for RateLimitMiddleware."""
import json
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from zeno.ratelimit.backends import MemoryRateLimitBackend
from zeno.ratelimit.middleware import RateLimitMiddleware, RateLimitRule


def build_app(backend, *, anon_limit=5, anon_window=60, user_limit=10, user_window=60, enabled=True):
    async def hello(request: Request):
        return JSONResponse({"ok": True})

    routes = [Route("/api/posts", hello, methods=["GET"])]
    app = Starlette(routes=routes)
    app = RateLimitMiddleware(
        app,
        backend,
        anon_limit=anon_limit,
        anon_window=anon_window,
        user_limit=user_limit,
        user_window=user_window,
        enabled=enabled,
    )
    return app


def test_allows_within_limit():
    backend = MemoryRateLimitBackend()
    app = build_app(backend, anon_limit=3)
    client = TestClient(app)

    for _ in range(3):
        r = client.get("/api/posts")
        assert r.status_code == 200
        assert "x-ratelimit-limit" in r.headers


def test_rejects_over_limit():
    backend = MemoryRateLimitBackend()
    app = build_app(backend, anon_limit=2)
    client = TestClient(app)

    client.get("/api/posts")
    client.get("/api/posts")
    r = client.get("/api/posts")
    assert r.status_code == 429
    assert "retry-after" in r.headers
    body = r.json()
    assert body["error"] == "Rate limit exceeded"


def test_remaining_header():
    backend = MemoryRateLimitBackend()
    app = build_app(backend, anon_limit=5)
    client = TestClient(app)

    r = client.get("/api/posts")
    assert r.headers["x-ratelimit-remaining"] == "4"
    r2 = client.get("/api/posts")
    assert r2.headers["x-ratelimit-remaining"] == "3"


def test_disabled_middleware():
    backend = MemoryRateLimitBackend()
    app = build_app(backend, anon_limit=1, enabled=False)
    client = TestClient(app)

    for _ in range(10):
        r = client.get("/api/posts")
        assert r.status_code == 200
        assert "x-ratelimit-limit" not in r.headers


def test_fail_open_on_backend_error(monkeypatch):
    backend = MemoryRateLimitBackend()

    async def boom(*args, **kwargs):
        raise RuntimeError("backend down")

    monkeypatch.setattr(backend, "check", boom)
    app = build_app(backend)
    client = TestClient(app)

    r = client.get("/api/posts")
    assert r.status_code == 200  # fail-open


def test_per_route_rule():
    backend = MemoryRateLimitBackend()
    app = build_app(backend, anon_limit=100)  # high global default

    # Add a tight rule just for /api/posts
    rl_mw = app  # the outermost middleware
    rl_mw.add_rule(RateLimitRule("/api/posts", limit=2, window=60))

    client = TestClient(app)
    client.get("/api/posts")
    client.get("/api/posts")
    r = client.get("/api/posts")
    assert r.status_code == 429


def test_ratelimit_headers_on_allowed():
    backend = MemoryRateLimitBackend()
    app = build_app(backend, anon_limit=10)
    client = TestClient(app)

    r = client.get("/api/posts")
    assert r.status_code == 200
    assert "x-ratelimit-limit" in r.headers
    assert "x-ratelimit-remaining" in r.headers
    assert "x-ratelimit-reset" in r.headers
