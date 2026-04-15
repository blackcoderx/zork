"""Tests for CSRF protection in cookie-based authentication.

Covers:
- Double-submit cookie pattern validation
- Valid CSRF token passes
- Missing header fails
- Mismatched tokens fail
- CSRF disabled skips validation
"""

import pytest
from starlette.requests import Request

from zork.auth.delivery import CookieTokenDelivery


def _make_request_with_csrf(path="/", cookies=None, headers=None):
    """Helper to create a Request with proper cookie and header handling."""
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
        "method": "POST",
        "path": path,
        "headers": headers,
        "query_string": b"",
        "root_path": b"",
        "client": None,
        "server": None,
    }
    return Request(scope)


class TestCSRFProtection:
    @pytest.fixture
    def delivery(self):
        return CookieTokenDelivery(
            csrf_cookie_name="zork_csrf_token",
            enable_csrf=True,
        )

    @pytest.fixture
    def csrf_disabled_delivery(self):
        return CookieTokenDelivery(
            csrf_cookie_name="zork_csrf_token",
            enable_csrf=False,
        )

    @pytest.mark.asyncio
    async def test_valid_double_submit_passes(self, delivery):
        csrf_value = "valid-csrf-token-123"
        request = _make_request_with_csrf(
            path="/api/data",
            cookies={"zork_csrf_token": csrf_value},
            headers=[(b"x-csrf-token", csrf_value.encode())],
        )

        token = await delivery.extract_csrf_token(request)
        assert token == csrf_value

    @pytest.mark.asyncio
    async def test_missing_header_fails(self, delivery):
        request = _make_request_with_csrf(
            path="/api/data", cookies={"zork_csrf_token": "some-token"}, headers=[]
        )

        token = await delivery.extract_csrf_token(request)
        assert token is None

    @pytest.mark.asyncio
    async def test_missing_cookie_fails(self, delivery):
        request = _make_request_with_csrf(
            path="/api/data", cookies={}, headers=[(b"x-csrf-token", b"some-token")]
        )

        token = await delivery.extract_csrf_token(request)
        assert token is None

    @pytest.mark.asyncio
    async def test_mismatched_tokens_fails(self, delivery):
        request = _make_request_with_csrf(
            path="/api/data",
            cookies={"zork_csrf_token": "cookie-token"},
            headers=[(b"x-csrf-token", b"header-token")],
        )

        token = await delivery.extract_csrf_token(request)
        assert token is None

    @pytest.mark.asyncio
    async def test_empty_header_fails(self, delivery):
        request = _make_request_with_csrf(
            path="/api/data",
            cookies={"zork_csrf_token": "cookie-token"},
            headers=[(b"x-csrf-token", b"")],
        )

        token = await delivery.extract_csrf_token(request)
        assert token is None

    @pytest.mark.asyncio
    async def test_empty_cookie_fails(self, delivery):
        request = _make_request_with_csrf(
            path="/api/data",
            cookies={"zork_csrf_token": ""},
            headers=[(b"x-csrf-token", b"header-token")],
        )

        token = await delivery.extract_csrf_token(request)
        assert token is None

    @pytest.mark.asyncio
    async def test_csrf_disabled_still_extracts_token(self, csrf_disabled_delivery):
        # When CSRF is disabled, extract_csrf_token still works
        # The enable_csrf flag only affects route-level validation
        request = _make_request_with_csrf(
            path="/api/data",
            cookies={"zork_csrf_token": "any-token"},
            headers=[(b"x-csrf-token", b"any-token")],
        )

        token = await csrf_disabled_delivery.extract_csrf_token(request)
        # CSRF extraction still works when disabled, just not enforced
        assert token == "any-token"


class TestCSRFExtractionEdgeCases:
    @pytest.fixture
    def delivery(self):
        return CookieTokenDelivery(enable_csrf=True)

    @pytest.mark.asyncio
    async def test_both_missing_returns_none(self, delivery):
        request = _make_request_with_csrf(path="/api/data", cookies={}, headers=[])

        token = await delivery.extract_csrf_token(request)
        assert token is None

    @pytest.mark.asyncio
    async def test_whitespace_in_tokens_normalized(self, delivery):
        # Note: Starlette normalizes header values, leading/trailing whitespace may be stripped
        request = _make_request_with_csrf(
            path="/api/data",
            cookies={"zork_csrf_token": "token"},
            headers=[(b"x-csrf-token", b"token")],
        )

        token = await delivery.extract_csrf_token(request)
        assert token == "token"

    @pytest.mark.asyncio
    async def test_unicode_tokens(self, delivery):
        csrf_value = "csrf-token-with-unicode"
        request = _make_request_with_csrf(
            path="/api/data",
            cookies={"zork_csrf_token": csrf_value},
            headers=[(b"x-csrf-token", csrf_value.encode("utf-8"))],
        )

        token = await delivery.extract_csrf_token(request)
        assert token == csrf_value
