from __future__ import annotations

from abc import ABC, abstractmethod

from starlette.requests import Request
from starlette.responses import Response


class TokenDeliveryBackend(ABC):
    """Abstract base class for token delivery mechanisms.

    Implementations handle how tokens are attached to responses and
    extracted from requests.
    """

    @property
    def supports_csrf(self) -> bool:
        """Whether this delivery method requires CSRF protection.

        Cookie-based delivery typically requires CSRF protection,
        while Bearer tokens do not.
        """
        return False

    @abstractmethod
    async def extract_token(self, request: Request) -> str | None:
        """Extract the access token from the request.

        Args:
            request: The incoming HTTP request.

        Returns:
            The token string if found, None otherwise.
        """
        ...

    @abstractmethod
    async def attach_token(
        self, response: Response, access_token: str, refresh_token: str | None = None
    ) -> None:
        """Attach token(s) to the response.

        Args:
            response: The HTTP response to attach tokens to.
            access_token: The access token to attach.
            refresh_token: The refresh token to attach (optional).
        """
        ...

    @abstractmethod
    async def clear_token(self, response: Response) -> None:
        """Clear tokens from the response (e.g., on logout).

        Args:
            response: The HTTP response to clear tokens from.
        """
        ...
