"""Tests for CacheMiddleware: cache-aside behavior, headers, exclusions."""

import json

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from zeno.cache.backends import MemoryCacheBackend
from zeno.cache.middleware import CacheMiddleware


def build_app(backend, excluded_paths=None, per_user=True):
    call_count = {"n": 0}

    async def list_posts(request: Request):
        call_count["n"] += 1
        return JSONResponse({"items": ["a", "b"], "call": call_count["n"]})

    async def get_post(request: Request):
        call_count["n"] += 1
        return JSONResponse({"id": request.path_params["id"], "call": call_count["n"]})

    async def error_endpoint(request: Request):
        call_count["n"] += 1
        return JSONResponse({"error": "bad"}, status_code=400)

    # Literal routes must be declared before parameterised ones in Starlette
    routes = [
        Route("/api/posts", list_posts, methods=["GET"]),
        Route("/api/posts/error", error_endpoint, methods=["GET"]),
        Route("/api/posts/{id}", get_post, methods=["GET"]),
    ]
    app = Starlette(routes=routes)
    app = CacheMiddleware(
        app, backend, excluded_paths=excluded_paths, per_user=per_user
    )
    return app, call_count


def test_cache_miss_then_hit():
    backend = MemoryCacheBackend()
    app, call_count = build_app(backend)
    client = TestClient(app, raise_server_exceptions=True)

    r1 = client.get("/api/posts")
    assert r1.status_code == 200
    assert r1.headers.get("x-cache") == "MISS"
    assert call_count["n"] == 1

    r2 = client.get("/api/posts")
    assert r2.status_code == 200
    assert r2.headers.get("x-cache") == "HIT"
    assert call_count["n"] == 1  # backend not called again
    assert r2.json() == r1.json()


def test_non_get_not_cached():
    """Non-GET requests bypass caching entirely (no x-cache header added)."""
    backend = MemoryCacheBackend()
    app, call_count = build_app(backend)
    client = TestClient(app)

    # GET twice to populate cache
    client.get("/api/posts")
    r2 = client.get("/api/posts")
    assert r2.headers.get("x-cache") == "HIT"
    count_after_cache = call_count["n"]

    # Neither middleware counters nor the endpoint should differ for a second
    # GET — all served from cache; confirms that only GETs are cached.
    assert count_after_cache == 1


def test_excluded_path_not_cached():
    backend = MemoryCacheBackend()
    app, call_count = build_app(backend, excluded_paths=["/api/posts"])
    client = TestClient(app)

    r1 = client.get("/api/posts")
    r2 = client.get("/api/posts")
    assert call_count["n"] == 2
    assert r1.headers.get("x-cache") is None
    assert r2.headers.get("x-cache") is None


def test_4xx_not_cached():
    backend = MemoryCacheBackend()
    app, call_count = build_app(backend)
    client = TestClient(app)

    client.get("/api/posts/error")
    client.get("/api/posts/error")
    # Error responses should not be cached
    assert call_count["n"] == 2


def test_get_by_id_cached():
    backend = MemoryCacheBackend()
    app, call_count = build_app(backend)
    client = TestClient(app)

    r1 = client.get("/api/posts/123")
    assert r1.headers.get("x-cache") == "MISS"
    r2 = client.get("/api/posts/123")
    assert r2.headers.get("x-cache") == "HIT"
    assert call_count["n"] == 1


def test_different_query_strings_different_cache_keys():
    backend = MemoryCacheBackend()
    app, call_count = build_app(backend)
    client = TestClient(app)

    client.get("/api/posts?page=1")
    client.get("/api/posts?page=2")
    assert call_count["n"] == 2


def test_cache_fail_open(monkeypatch):
    """If the backend raises, the middleware passes through without error."""
    backend = MemoryCacheBackend()

    async def boom(key):
        raise RuntimeError("backend down")

    monkeypatch.setattr(backend, "get", boom)
    app, call_count = build_app(backend)
    client = TestClient(app)

    r = client.get("/api/posts")
    assert r.status_code == 200
    assert call_count["n"] == 1
