from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from zork.auth.delivery.base import TokenDeliveryBackend


class BearerTokenDelivery(TokenDeliveryBackend):
    """Bearer token delivery via Authorization header.

    This is the default delivery mechanism where the access token
    is returned in the response body and sent via the Authorization header.
    """

    @property
    def supports_csrf(self) -> bool:
        return False

    async def extract_token(self, request: Request) -> str | None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return None

    async def attach_token(
        self, response: Response, access_token: str, refresh_token: str | None = None
    ) -> None:
        pass

    async def clear_token(self, response: Response) -> None:
        pass
