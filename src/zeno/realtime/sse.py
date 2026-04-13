from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, AsyncGenerator

from starlette.requests import Request
from starlette.responses import StreamingResponse

from cinder.errors import CinderError
from cinder.realtime.auth import authenticate_ws_token
from cinder.realtime.auth_filter import filter_for_rule

if TYPE_CHECKING:
    from cinder.realtime import RealtimeFacade

logger = logging.getLogger("cinder.realtime.sse")

# How often to send an SSE comment heartbeat (seconds).
# Keeps proxies and load balancers from killing idle connections.
# Override via the CINDER_SSE_HEARTBEAT env var or by patching this module in tests.
import os
HEARTBEAT_INTERVAL: float = float(os.getenv("CINDER_SSE_HEARTBEAT", "15"))


def sse_endpoint_factory(facade: "RealtimeFacade", db, secret: str):
    """Return the SSE HTTP handler bound to this app's realtime facade.

    Called once from ``Cinder.build()``; the resulting coroutine is registered
    as a ``Route`` with ``methods=["GET"]``.

    Query parameters:
    - ``token``   — JWT bearer token (required unless collection is public)
    - ``channel`` — one or more channel names to subscribe to (repeatable)

    Example::

        GET /api/realtime/sse?token=<jwt>&channel=collection:posts&channel=collection:comments
    """

    async def sse_endpoint(request: Request) -> StreamingResponse:
        # ------------------------------------------------------------------
        # 1. Authenticate
        # ------------------------------------------------------------------
        user = None
        token = request.query_params.get("token")
        if token:
            try:
                user = await authenticate_ws_token(token, db, secret)
            except CinderError as e:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    {"status": e.status_code, "error": e.message},
                    status_code=e.status_code,
                )

        # ------------------------------------------------------------------
        # 2. Collect requested channels
        # ------------------------------------------------------------------
        channels = request.query_params.getlist("channel")
        if not channels:
            from starlette.responses import JSONResponse
            return JSONResponse(
                {"status": 400, "error": "At least one channel is required"},
                status_code=400,
            )

        # ------------------------------------------------------------------
        # 3. Subscribe and build per-channel filters
        # ------------------------------------------------------------------
        # For built-in collection channels, attach the read-rule filter.
        # Custom channels get no default filter (public by default).
        combined_filter = _build_filter(channels, facade, user)
        subscription = await facade.broker.subscribe(
            channels, user=user, filter=combined_filter
        )

        # ------------------------------------------------------------------
        # 4. Stream
        # ------------------------------------------------------------------
        async def event_generator() -> AsyncGenerator[bytes, None]:
            # SSE preamble headers are set on the response; nothing to yield.
            try:
                while True:
                    try:
                        envelope = await asyncio.wait_for(
                            subscription.get(), timeout=HEARTBEAT_INTERVAL
                        )
                    except asyncio.TimeoutError:
                        # Heartbeat — SSE comment line; ignored by browsers
                        yield b": ping\n\n"
                        continue

                    if envelope is None:
                        # Broker closed (app:shutdown)
                        return

                    # Format as SSE frame
                    data = json.dumps(envelope)
                    event_type = envelope.get("event", "message")
                    record_id = envelope.get("id", "")
                    frame = (
                        f"event: {event_type}\n"
                        f"data: {data}\n"
                        f"id: {record_id}\n\n"
                    )
                    yield frame.encode()

            except asyncio.CancelledError:
                # Client disconnected
                pass
            finally:
                await facade.broker.unsubscribe(subscription)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            },
        )

    return sse_endpoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_filter(channels: list[str], facade: "RealtimeFacade", user: dict | None):
    """Build a combined filter that applies per-collection auth rules for
    built-in ``collection:{name}`` channels.  Custom channels pass through."""
    # Collect per-channel filters
    channel_filters: dict[str, object] = {}
    for channel in channels:
        if not channel.startswith("collection:"):
            continue
        name = channel.removeprefix("collection:")
        collections = facade._collections
        if name not in collections:
            continue
        _, auth_rules = collections[name]
        read_rule = auth_rules.get("read", "public")
        channel_filters[channel] = filter_for_rule(read_rule)

    if not channel_filters:
        return None  # all custom channels — no filter

    def combined(envelope: dict, u: dict | None) -> bool:
        ch = envelope.get("channel", "")
        f = channel_filters.get(ch)
        if f is None:
            return True  # custom channel — allow
        return f(envelope, u)  # type: ignore[return-value]

    return combined
