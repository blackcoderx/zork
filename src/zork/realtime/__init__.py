from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from starlette.routing import Route, WebSocketRoute

from zork.realtime.bridge import default_envelope
from zork.realtime.bridge import install as install_bridge
from zork.realtime.broker import RealtimeBroker
from zork.realtime.sse import sse_endpoint_factory
from zork.realtime.websocket import ws_endpoint_factory

if TYPE_CHECKING:
    pass

logger = logging.getLogger("zork.realtime")

__all__ = [
    "RealtimeFacade",
    "RealtimeBroker",
]


class RealtimeFacade:
    """Public surface for the Zork realtime layer.

    Attached to the ``Zork`` app as ``app.realtime``.

    **Developer-facing API:**

    .. code-block:: python

        # Publish a fully custom event to any channel
        await app.realtime.publish("fraud:detected", {"score": 0.95})

        # Opt out of auto-emit for a specific collection
        app.realtime.disable_auto_emit("audit_logs")

        # Override the envelope shape for all auto-emitted events
        app.realtime.envelope_builder = my_envelope_fn

        # Add a custom WebSocket route (your own protocol)
        app.realtime.add_websocket_route("/api/chat", my_ws_handler)

        # Direct broker access for advanced use-cases
        sub = await app.realtime.broker.subscribe(["fraud:detected"])
        async for envelope in sub:
            ...
    """

    def __init__(self, broker: RealtimeBroker, app_ref) -> None:
        self.broker: RealtimeBroker = broker

        self.enabled: bool = True

        self.envelope_builder: Callable = default_envelope

        self._collections: dict = {}

        self._app_ref = app_ref

        self._disabled: set[str] = set()

        self._extra_ws_routes: list[tuple[str, Any]] = []

        self._cors_config: dict = {"allow_origins": "*", "allow_origin_regex": None}

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    async def publish(
        self, channel: str, payload: Any, *, event: str | None = None
    ) -> None:
        """Publish an arbitrary payload to *channel*.

        Wraps the payload in a minimal envelope if it is not already one.
        You can call this from any hook, background task, or custom handler.
        """
        if isinstance(payload, dict) and "channel" in payload:
            envelope = payload  # already an envelope
        else:
            envelope = {
                "channel": channel,
                "event": event or "message",
                "data": payload,
            }
        await self.broker.publish(channel, envelope)

    def disable_auto_emit(self, collection: str) -> None:
        """Stop the bridge from broadcasting events for *collection*.

        Must be called **before** ``app.build()``.  Has no effect after
        the bridge is installed.
        """
        self._disabled.add(collection)

    def enable_auto_emit(self, collection: str) -> None:
        """Re-enable auto-emit for *collection* (reverses ``disable_auto_emit``)."""
        self._disabled.discard(collection)

    def add_websocket_route(self, path: str, handler) -> None:
        """Register a custom WebSocket route alongside the built-in one.

        The route is added to the Starlette app during ``build()``.
        """
        self._extra_ws_routes.append((path, handler))

    def configure_cors(
        self,
        allow_origins: str | list[str] = "*",
        allow_origin_regex: str | None = None,
    ) -> None:
        """Configure CORS settings for SSE endpoint.

        Args:
            allow_origins: Origin(s) to allow. Defaults to "*" (backward compatible).
            allow_origin_regex: Optional regex pattern to validate origins dynamically.
        """
        if isinstance(allow_origins, str):
            self._cors_config = {"allow_origins": allow_origins, "allow_origin_regex": allow_origin_regex}
        else:
            self._cors_config = {"allow_origins": list(allow_origins), "allow_origin_regex": allow_origin_regex}

    def configure_origin_check(self, enabled: bool = True, origin_regex: str | None = None) -> None:
        """Configure WebSocket origin validation.

        Args:
            enabled: If True, validate Origin header against origin_regex (disabled by default).
            origin_regex: Regex pattern to validate origins.
        """
        self._origin_check = enabled
        self._origin_regex = origin_regex

    # ------------------------------------------------------------------
    # Internal: called from Zork.build()
    # ------------------------------------------------------------------

    def _build_routes(self, db, secret: str, prefix: str | None = None) -> list:
        """Return the list of Starlette routes for the realtime layer."""
        realtime_prefix = f"{prefix}/realtime" if prefix else "/api/realtime"
        origin_check = getattr(self, "_origin_check", False)
        origin_regex = getattr(self, "_origin_regex", None)
        routes = [
            WebSocketRoute(realtime_prefix, ws_endpoint_factory(self, db, secret, origin_check, origin_regex)),
            Route(
                f"{realtime_prefix}/sse",
                sse_endpoint_factory(self, db, secret, cors_config=self._cors_config),
                methods=["GET"],
            ),
        ]
        for path, handler in self._extra_ws_routes:
            routes.append(WebSocketRoute(path, handler))
        return routes

    def _install_bridge(self, registry, collections: dict) -> None:
        """Wire the auto-emit handlers into the hook registry."""
        self._collections = collections
        if not self.enabled:
            return
        install_bridge(
            registry,
            collections,
            self.broker,
            disabled=self._disabled,
            envelope_builder=self.envelope_builder,
        )
