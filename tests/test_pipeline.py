import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from zeno.errors import ZenoError
from zeno.pipeline import build_middleware_stack


async def ok_endpoint(request: Request):
    return JSONResponse({"ok": True})


async def error_endpoint(request: Request):
    raise ZenoError(400, "Validation failed")


async def unhandled_error_endpoint(request: Request):
    raise ValueError("unexpected")


def create_test_app(routes):
    app = Starlette(routes=routes)
    app = build_middleware_stack(app)
    return app


class TestErrorHandler:
    def test_zeno_error_returns_json(self):
        app = create_test_app([Route("/err", error_endpoint)])
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/err")
        assert resp.status_code == 400
        assert resp.json() == {"status": 400, "error": "Validation failed"}

    def test_unhandled_error_returns_500(self):
        app = create_test_app([Route("/boom", unhandled_error_endpoint)])
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/boom")
        assert resp.status_code == 500
        assert resp.json()["status"] == 500

    def test_success_passes_through(self):
        app = create_test_app([Route("/ok", ok_endpoint)])
        client = TestClient(app)
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


class TestRequestID:
    def test_response_has_request_id_header(self):
        app = create_test_app([Route("/ok", ok_endpoint)])
        client = TestClient(app)
        resp = client.get("/ok")
        assert "x-request-id" in resp.headers
        req_id = resp.headers["x-request-id"]
        assert len(req_id) == 36


class TestCORS:
    def test_cors_headers_present(self):
        app = create_test_app([Route("/ok", ok_endpoint)])
        client = TestClient(app)
        resp = client.options(
            "/ok",
            headers={
                "origin": "http://localhost:3000",
                "access-control-request-method": "GET",
            },
        )
        assert "access-control-allow-origin" in resp.headers
