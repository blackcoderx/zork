from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from cinder.errors import CinderError
from cinder.realtime.auth import authenticate_ws_token
from cinder.realtime.auth_filter import filter_for_rule

if TYPE_CHECKING:
    from cinder.realtime import RealtimeFacade

logger = logging.getLogger("cinder.realtime.websocket")

# How often the server sends a ping frame to keep the connection alive (seconds)
PING_INTERVAL = 30


def ws_endpoint_factory(facade: "RealtimeFacade", db, secret: str):
    """Return the WebSocket ASGI endpoint closure bound to this app's
    realtime facade, database, and JWT secret.

    Called once from ``Cinder.build()``; the resulting coroutine is registered
    as a ``WebSocketRoute``.
    """

    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()

        # ------------------------------------------------------------------
        # 1. Authenticate via query-string token (optional)
        # ------------------------------------------------------------------
        # Clients may also authenticate mid-session by sending
        # {"action":"auth","token":"<jwt>"} at any point before subscribing.
        # The reader loop handles that action like any other message.
        user = None
        token = websocket.query_params.get("token")

        if token:
            try:
                user = await authenticate_ws_token(token, db, secret)
            except CinderError as e:
                await websocket.close(code=1008, reason=e.message)
                return

        # ------------------------------------------------------------------
        # 2. Main reader/writer loop
        # ------------------------------------------------------------------
        subscription = None
        reader_task = None
        writer_task = None

        try:
            # One subscription object; channels are added/removed dynamically.
            # user_ref is a mutable container so the reader can upgrade
            # identity mid-session via {"action":"auth","token":"..."}.
            user_ref: list = [user]
            subscription = await facade.broker.subscribe([], user=user)

            async def reader():
                """Process incoming messages from the client."""
                while True:
                    try:
                        raw = await websocket.receive_text()
                    except WebSocketDisconnect:
                        return
                    except Exception:
                        return
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        await _send(websocket, {"type": "error", "message": "Invalid JSON"})
                        continue

                    action = msg.get("action")

                    if action == "auth":
                        # Mid-session authentication (or re-auth)
                        try:
                            authed = await authenticate_ws_token(
                                msg.get("token", ""), db, secret
                            )
                        except CinderError as e:
                            await _send(websocket, {"type": "error", "message": e.message})
                            continue
                        user_ref[0] = authed
                        subscription.user = authed
                        await _send(websocket, {"type": "ack", "action": "auth"})

                    elif action == "subscribe":
                        channel = msg.get("channel", "")
                        if not channel:
                            await _send(websocket, {"type": "error", "message": "Missing channel"})
                            continue

                        # Attach auth filter if subscribing to a collection channel
                        _maybe_attach_filter(channel, subscription, facade, user)

                        if channel not in subscription.channels:
                            subscription.channels.append(channel)
                        await _send(websocket, {"type": "ack", "action": "subscribe", "channel": channel})

                    elif action == "unsubscribe":
                        channel = msg.get("channel", "")
                        try:
                            subscription.channels.remove(channel)
                        except ValueError:
                            pass
                        await _send(websocket, {"type": "ack", "action": "unsubscribe", "channel": channel})

                    elif action == "ping":
                        await _send(websocket, {"type": "pong"})

                    else:
                        await _send(websocket, {"type": "error", "message": f"Unknown action: {action}"})

            async def writer():
                """Push broker envelopes to the client, with periodic pings."""
                while True:
                    try:
                        envelope = await asyncio.wait_for(
                            subscription.get(), timeout=PING_INTERVAL
                        )
                    except asyncio.TimeoutError:
                        # Send a server-initiated ping to keep connection alive
                        try:
                            await _send(websocket, {"type": "ping"})
                        except Exception:
                            return
                        continue

                    if envelope is None:
                        # Broker closed
                        return

                    try:
                        await _send(websocket, {"type": "envelope", **envelope})
                    except Exception:
                        return

            reader_task = asyncio.create_task(reader())
            writer_task = asyncio.create_task(writer())

            done, pending = await asyncio.wait(
                [reader_task, writer_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.exception("WebSocket error: %s", exc)
        finally:
            if reader_task:
                reader_task.cancel()
            if writer_task:
                writer_task.cancel()
            if subscription is not None:
                await facade.broker.unsubscribe(subscription)
            if websocket.client_state != WebSocketState.DISCONNECTED:
                try:
                    await websocket.close()
                except Exception:
                    pass

    return ws_endpoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _send(ws: WebSocket, data: dict) -> None:
    await ws.send_text(json.dumps(data))


def _maybe_attach_filter(
    channel: str,
    subscription,
    facade: "RealtimeFacade",
    user: dict | None,
) -> None:
    """If *channel* is a built-in ``collection:{name}`` channel, attach the
    read-rule filter automatically — unless the developer already set a custom
    filter on the subscription."""
    if subscription.filter is not None:
        return  # already has a custom filter

    if not channel.startswith("collection:"):
        return  # custom channel — no default filter

    collection_name = channel.removeprefix("collection:")
    collections = facade._collections
    if collection_name not in collections:
        return

    _, auth_rules = collections[collection_name]
    read_rule = auth_rules.get("read", "public")
    subscription.filter = filter_for_rule(read_rule)
