"""Tests for token delivery backends.

Covers:
- BearerTokenDelivery extract/attach/clear operations
- CookieTokenDelivery extract/attach/clear operations
- Cookie settings (secure, samesite, httponly)
"""

import pytest
from starlette.datastructures import Headers, URL
from starlette.requests import Request
from starlette.responses import Response

from zork.auth.delivery import (
    BearerTokenDelivery,
    CookieTokenDelivery,
    TokenDeliveryBackend,
)


class TestBearerTokenDelivery:
    @pytest.fixture
    def delivery(self):
        return BearerTokenDelivery()

    @pytest.mark.asyncio
    async def test_extract_from_header(self, delivery):
        request = Request(
            scope={
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"authorization", b"Bearer test-token-123")],
            }
        )

        token = await delivery.extract_token(request)
        assert token == "test-token-123"

    @pytest.mark.asyncio
    async def test_missing_header_returns_none(self, delivery):
        request = Request(
            scope={
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [],
            }
        )

        token = await delivery.extract_token(request)
        assert token is None

    @pytest.mark.asyncio
    async def test_wrong_scheme_returns_none(self, delivery):
        request = Request(
            scope={
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"authorization", b"Basic dXNlcjpwYXNz")],
            }
        )

        token = await delivery.extract_token(request)
        assert token is None

    @pytest.mark.asyncio
    async def test_attach_token_is_noop(self, delivery):
        response = Response(content="")
        await delivery.attach_token(response, "access-token", "refresh-token")
        assert response.body == b""

    @pytest.mark.asyncio
    async def test_clear_token_is_noop(self, delivery):
        response = Response(content="")
        await delivery.clear_token(response)
        assert response.body == b""

    @pytest.mark.asyncio
    async def test_supports_csrf_is_false(self, delivery):
        assert delivery.supports_csrf is False

    def test_implements_interface(self, delivery):
        assert isinstance(delivery, TokenDeliveryBackend)


def _make_request_with_cookies(path="/", cookies=None, headers=None):
    """Helper to create a Request with proper cookie handling."""
    if cookies is None:
        cookies = {}
    if headers is None:
        headers = []

    # Build cookie headers from cookies dict
    cookie_parts = [f"{k}={v}" for k, v in cookies.items()]
    if cookie_parts:
        headers.append((b"cookie", "; ".join(cookie_parts).encode()))

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers,
        "query_string": b"",
        "root_path": b"",
        "client": None,
        "server": None,
    }
    return Request(scope)


class TestCookieTokenDelivery:
    @pytest.fixture
    def delivery(self):
        return CookieTokenDelivery(
            access_cookie_name="test_access",
            refresh_cookie_name="test_refresh",
            csrf_cookie_name="test_csrf",
            secure=False,
            samesite="lax",
            domain=None,
            access_max_age=3600,
            refresh_max_age=604800,
            csrf_max_age=86400,
            enable_csrf=True,
        )

    @pytest.mark.asyncio
    async def test_extract_from_cookie(self, delivery):
        request = _make_request_with_cookies(
            cookies={"test_access": "cookie-access-token"}
        )

        token = await delivery.extract_token(request)
        assert token == "cookie-access-token"

    @pytest.mark.asyncio
    async def test_extract_missing_cookie_returns_none(self, delivery):
        request = _make_request_with_cookies(cookies={})

        token = await delivery.extract_token(request)
        assert token is None

    @pytest.mark.asyncio
    async def test_extract_refresh_token(self, delivery):
        request = _make_request_with_cookies(
            path="/api/auth/refresh", cookies={"test_refresh": "refresh-token-value"}
        )

        token = await delivery.extract_refresh_token(request)
        assert token == "refresh-token-value"

    @pytest.mark.asyncio
    async def test_attach_tokens_sets_cookies(self, delivery):
        response = Response(content="")
        await delivery.attach_token(response, "access-token", "refresh-token")

        # Response should have multiple Set-Cookie headers
        assert len(response.headers.getlist("set-cookie")) >= 2

    @pytest.mark.asyncio
    async def test_attach_access_cookie_contains_token(self, delivery):
        response = Response(content="")
        await delivery.attach_token(response, "access-token", None)

        set_cookie_headers = response.headers.getlist("set-cookie")
        access_cookie = [
            h for h in set_cookie_headers if "test_access=access-token" in h
        ]
        assert len(access_cookie) == 1

    @pytest.mark.asyncio
    async def test_attach_refresh_cookie_contains_token(self, delivery):
        response = Response(content="")
        await delivery.attach_token(response, "access-token", "refresh-token")

        set_cookie_headers = response.headers.getlist("set-cookie")
        refresh_cookie = [
            h for h in set_cookie_headers if "test_refresh=refresh-token" in h
        ]
        assert len(refresh_cookie) == 1

    @pytest.mark.asyncio
    async def test_access_cookie_is_httponly(self, delivery):
        response = Response(content="")
        await delivery.attach_token(response, "access-token", None)

        set_cookie_headers = response.headers.getlist("set-cookie")
        access_cookie = [h for h in set_cookie_headers if "test_access=" in h][0]
        assert "HttpOnly" in access_cookie

    @pytest.mark.asyncio
    async def test_refresh_cookie_is_httponly(self, delivery):
        response = Response(content="")
        await delivery.attach_token(response, "access-token", "refresh-token")

        set_cookie_headers = response.headers.getlist("set-cookie")
        refresh_cookie = [h for h in set_cookie_headers if "test_refresh=" in h][0]
        assert "HttpOnly" in refresh_cookie

    @pytest.mark.asyncio
    async def test_csrf_cookie_created(self, delivery):
        response = Response(content="")
        await delivery.attach_token(response, "access-token", "refresh-token")

        set_cookie_headers = response.headers.getlist("set-cookie")
        csrf_cookie = [h for h in set_cookie_headers if "test_csrf=" in h]
        assert len(csrf_cookie) == 1

    @pytest.mark.asyncio
    async def test_csrf_cookie_not_httponly(self, delivery):
        response = Response(content="")
        await delivery.attach_token(response, "access-token", "refresh-token")

        set_cookie_headers = response.headers.getlist("set-cookie")
        csrf_cookie = [h for h in set_cookie_headers if "test_csrf=" in h][0]
        assert "HttpOnly" not in csrf_cookie

    @pytest.mark.asyncio
    async def test_clear_tokens_deletes_cookies(self, delivery):
        response = Response(content="")
        await delivery.clear_token(response)

        set_cookie_headers = response.headers.getlist("set-cookie")
        assert len(set_cookie_headers) >= 2

    @pytest.mark.asyncio
    async def test_supports_csrf_is_true_when_enabled(self, delivery):
        assert delivery.supports_csrf is True

    @pytest.mark.asyncio
    async def test_supports_csrf_is_false_when_disabled(self):
        delivery = CookieTokenDelivery(enable_csrf=False)
        assert delivery.supports_csrf is False

    @pytest.mark.asyncio
    async def test_secure_cookie_setting(self):
        delivery = CookieTokenDelivery(secure=True, samesite="strict")
        response = Response(content="")
        await delivery.attach_token(response, "secure-token", None)

        set_cookie_headers = response.headers.getlist("set-cookie")
        cookie = set_cookie_headers[0]
        assert "Secure" in cookie
        assert "SameSite=strict" in cookie

    @pytest.mark.asyncio
    async def test_domain_cookie_setting(self):
        delivery = CookieTokenDelivery(domain=".example.com")
        response = Response(content="")
        await delivery.attach_token(response, "domain-token", None)

        set_cookie_headers = response.headers.getlist("set-cookie")
        cookie = set_cookie_headers[0]
        assert "Domain=.example.com" in cookie

    @pytest.mark.asyncio
    async def test_refresh_path_is_strict(self, delivery):
        response = Response(content="")
        await delivery.attach_token(response, "access-token", "refresh-token")

        set_cookie_headers = response.headers.getlist("set-cookie")
        refresh_cookie = [h for h in set_cookie_headers if "test_refresh=" in h][0]
        assert "Path=/api/auth/refresh" in refresh_cookie

    def test_implements_interface(self, delivery):
        assert isinstance(delivery, TokenDeliveryBackend)

    def test_default_cookie_names(self):
        delivery = CookieTokenDelivery()
        assert delivery._access_cookie_name == "zork_access_token"
        assert delivery._refresh_cookie_name == "zork_refresh_token"
        assert delivery._csrf_cookie_name == "zork_csrf_token"

    def test_default_settings(self):
        delivery = CookieTokenDelivery()
        assert delivery._secure is True
        assert delivery._samesite == "lax"
        assert delivery._access_max_age == 3600
        assert delivery._refresh_max_age == 604800
        assert delivery._csrf_max_age == 86400
        assert delivery._enable_csrf is True


class TestTokenDeliveryBackendInterface:
    def test_bearer_implements_interface(self):
        delivery = BearerTokenDelivery()
        assert isinstance(delivery, TokenDeliveryBackend)

    def test_cookie_implements_interface(self):
        delivery = CookieTokenDelivery()
        assert isinstance(delivery, TokenDeliveryBackend)
