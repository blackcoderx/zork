from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from starlette.routing import Route, WebSocketRoute

from cinder.realtime.broker import RealtimeBroker
from cinder.realtime.bridge import default_envelope, install as install_bridge
from cinder.realtime.sse import sse_endpoint_factory
from cinder.realtime.websocket import ws_endpoint_factory

if TYPE_CHECKING:
    pass

logger = logging.getLogger("cinder.realtime")

__all__ = [
    "RealtimeFacade",
    "RealtimeBroker",
]


class RealtimeFacade:
    """Public surface for the Cinder realtime layer.

    Attached to the ``Cinder`` app as ``app.realtime``.

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

        # Set to False to disable all auto-emit (built-in CRUD → broker)
        self.enabled: bool = True

        # Override to change the envelope shape for all auto-emitted events
        self.envelope_builder: Callable = default_envelope

        # Internal: collections dict set by Cinder.build()
        self._collections: dict = {}

        # Internal: weak reference back to the Cinder app (for auth_rules lookup)
        self._app_ref = app_ref

        # Per-collection opt-out
        self._disabled: set[str] = set()

        # Developer-registered extra WebSocket routes
        self._extra_ws_routes: list[tuple[str, Any]] = []

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

    # ------------------------------------------------------------------
    # Internal: called from Cinder.build()
    # ------------------------------------------------------------------

    def _build_routes(self, db, secret: str) -> list:
        """Return the list of Starlette routes for the realtime layer."""
        routes = [
            WebSocketRoute("/api/realtime", ws_endpoint_factory(self, db, secret)),
            Route(
                "/api/realtime/sse",
                sse_endpoint_factory(self, db, secret),
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
