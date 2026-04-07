from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CinderContext:
    """Context passed to every hook handler.

    Carries the authenticated user (if any), a request id for correlation,
    the collection and operation being performed, and an ``extra`` dict for
    ad-hoc data. ``request`` is the Starlette ``Request`` when available.
    """

    user: dict | None = None
    request_id: str | None = None
    collection: str | None = None
    operation: str | None = None
    request: Any = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_request(
        cls,
        request: Any,
        *,
        collection: str | None = None,
        operation: str | None = None,
    ) -> "CinderContext":
        user = getattr(getattr(request, "state", None), "user", None)
        request_id = None
        scope = getattr(request, "scope", None)
        if scope is not None:
            state = scope.get("state") or {}
            request_id = state.get("request_id")
        return cls(
            user=user,
            request_id=request_id,
            collection=collection,
            operation=operation,
            request=request,
        )

    @classmethod
    def system(cls, **kwargs: Any) -> "CinderContext":
        return cls(**kwargs)
