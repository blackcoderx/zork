from __future__ import annotations

import secrets

from starlette.requests import Request
from starlette.responses import Response

from zork.auth.delivery.base import TokenDeliveryBackend


class CookieTokenDelivery(TokenDeliveryBackend):
    """HTTP-only cookie token delivery with CSRF protection.

    Uses the double-submit cookie pattern for CSRF protection:
    - Access token in HTTP-only cookie (short-lived)
    - Refresh token in HTTP-only cookie with strict path (long-lived)
    - CSRF token in readable cookie (for double-submit verification)

    Security features:
    - httponly=True prevents XSS from reading tokens
    - secure=True ensures HTTPS-only transmission
    - samesite restricts cross-site cookie sending
    - Strict path on refresh token limits its exposure
    - CSRF double-submit prevents cross-site request forgery
    """

    def __init__(
        self,
        access_cookie_name: str = "zork_access_token",
        refresh_cookie_name: str = "zork_refresh_token",
        csrf_cookie_name: str = "zork_csrf_token",
        secure: bool = True,
        samesite: str = "lax",
        domain: str | None = None,
        access_max_age: int = 3600,
        refresh_max_age: int = 604800,
        csrf_max_age: int = 86400,
        enable_csrf: bool = True,
    ) -> None:
        self._access_cookie_name = access_cookie_name
        self._refresh_cookie_name = refresh_cookie_name
        self._csrf_cookie_name = csrf_cookie_name
        self._secure = secure
        self._samesite = samesite
        self._domain = domain
        self._access_max_age = access_max_age
        self._refresh_max_age = refresh_max_age
        self._csrf_max_age = csrf_max_age
        self._enable_csrf = enable_csrf

    @property
    def supports_csrf(self) -> bool:
        return self._enable_csrf

    async def extract_token(self, request: Request) -> str | None:
        return request.cookies.get(self._access_cookie_name)

    async def extract_refresh_token(self, request: Request) -> str | None:
        return request.cookies.get(self._refresh_cookie_name)

    async def extract_csrf_token(self, request: Request) -> str | None:
        cookie_token = request.cookies.get(self._csrf_cookie_name)
        header_token = request.headers.get("X-CSRF-Token")
        if cookie_token and header_token and cookie_token == header_token:
            return cookie_token
        return None

    async def attach_token(
        self, response: Response, access_token: str, refresh_token: str | None = None
    ) -> None:
        response.set_cookie(
            key=self._access_cookie_name,
            value=access_token,
            max_age=self._access_max_age,
            secure=self._secure,
            samesite=self._samesite,
            domain=self._domain,
            path="/",
            httponly=True,
        )

        if refresh_token:
            response.set_cookie(
                key=self._refresh_cookie_name,
                value=refresh_token,
                max_age=self._refresh_max_age,
                secure=self._secure,
                samesite=self._samesite,
                domain=self._domain,
                path="/api/auth/refresh",
                httponly=True,
            )

        if self._enable_csrf:
            csrf_value = secrets.token_urlsafe(32)
            response.set_cookie(
                key=self._csrf_cookie_name,
                value=csrf_value,
                max_age=self._csrf_max_age,
                secure=self._secure,
                samesite=self._samesite,
                domain=self._domain,
                path="/",
                httponly=False,
            )

    async def clear_token(self, response: Response) -> None:
        response.delete_cookie(self._access_cookie_name, path="/")
        response.delete_cookie(self._refresh_cookie_name, path="/api/auth/refresh")
        response.delete_cookie(self._csrf_cookie_name, path="/")
