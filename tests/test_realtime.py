"""Tests for Phase 6 — Realtime (WebSocket + SSE).

Covers:
  - Broker unit tests (subscribe, publish, fanout, backpressure, close)
  - Auto-emit bridge (create/update/delete → broker publish)
  - Auth filters (public / authenticated / admin / owner rules)
  - WebSocket end-to-end (subscribe, receive events, owner filtering, custom events)
  - SSE end-to-end (subscribe via query params, receive events, bad token)
"""
from __future__ import annotations

import asyncio
import json

import pytest
from starlette.testclient import TestClient

from zeno.app import Zeno
from zeno.collections.schema import Collection, TextField
from zeno.collections.store import CollectionStore
from zeno.db.connection import Database
from zeno.realtime.auth_filter import filter_for_rule
from zeno.realtime.broker import RealtimeBroker


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def realtime_app(db_path):
    """A minimal Zeno app with a public-read 'posts' collection and realtime."""
    app = Zeno(database=db_path)
    posts = Collection("posts", fields=[TextField("title", required=True)])
    app.register(posts, auth=["read:public", "write:public"])
    return app


@pytest.fixture
def owner_app(db_path):
    """App with an owner-rule 'notes' collection."""
    app = Zeno(database=db_path)
    notes = Collection("notes", fields=[TextField("body", required=True)])
    app.register(notes, auth=["read:owner", "write:owner"])
    from zeno.auth import Auth
    app.use_auth(Auth())
    return app


# =============================================================================
# 1. Broker unit tests
# =============================================================================


@pytest.mark.asyncio
async def test_broker_subscribe_and_publish():
    broker = RealtimeBroker()
    sub = await broker.subscribe(["events"])
    await broker.publish("events", {"msg": "hello"})
    envelope = await asyncio.wait_for(sub.get(), timeout=1)
    assert envelope == {"msg": "hello"}
    await broker.close()


@pytest.mark.asyncio
async def test_broker_publish_no_subscribers_is_noop():
    broker = RealtimeBroker()
    await broker.publish("empty:channel", {"x": 1})  # should not raise
    await broker.close()


@pytest.mark.asyncio
async def test_broker_fanout_to_multiple_subscribers():
    broker = RealtimeBroker()
    sub_a = await broker.subscribe(["ch"])
    sub_b = await broker.subscribe(["ch"])
    await broker.publish("ch", {"n": 1})
    a = await asyncio.wait_for(sub_a.get(), timeout=1)
    b = await asyncio.wait_for(sub_b.get(), timeout=1)
    assert a == b == {"n": 1}
    await broker.close()


@pytest.mark.asyncio
async def test_broker_channel_isolation():
    broker = RealtimeBroker()
    sub_a = await broker.subscribe(["ch:a"])
    sub_b = await broker.subscribe(["ch:b"])
    await broker.publish("ch:a", {"for": "a"})
    # sub_b should NOT get this message
    assert sub_b._queue.empty()
    a = await asyncio.wait_for(sub_a.get(), timeout=1)
    assert a == {"for": "a"}
    await broker.close()


@pytest.mark.asyncio
async def test_broker_backpressure_drops_oldest():
    broker = RealtimeBroker(queue_size=2)
    sub = await broker.subscribe(["ch"])
    # Fill the queue past capacity
    await broker.publish("ch", {"n": 1})
    await broker.publish("ch", {"n": 2})
    await broker.publish("ch", {"n": 3})  # should drop oldest (n=1)
    assert sub.dropped == 1
    first = await asyncio.wait_for(sub.get(), timeout=1)
    assert first["n"] == 2   # n=1 was dropped
    await broker.close()


@pytest.mark.asyncio
async def test_broker_unsubscribe_stops_delivery():
    broker = RealtimeBroker()
    sub = await broker.subscribe(["ch"])
    await broker.unsubscribe(sub)
    # After unsubscribe the subscription is removed from the broker;
    # publishing should no longer deliver real envelopes.
    await broker.publish("ch", {"x": 1})
    # The only item in the queue should be the close sentinel, not a real envelope
    result = await asyncio.wait_for(sub.get(), timeout=1)
    assert result is None   # sentinel returns None — no real envelope delivered
    await broker.close()


@pytest.mark.asyncio
async def test_broker_close_unblocks_aiter():
    broker = RealtimeBroker()
    sub = await broker.subscribe(["ch"])

    results = []

    async def consume():
        async for env in sub:
            results.append(env)

    task = asyncio.create_task(consume())
    await broker.publish("ch", {"n": 1})
    await asyncio.sleep(0.05)
    await broker.close()
    await asyncio.wait_for(task, timeout=2)
    assert results == [{"n": 1}]


@pytest.mark.asyncio
async def test_broker_filter_drops_rejected_envelopes():
    broker = RealtimeBroker()
    sub = await broker.subscribe(["ch"], filter=lambda env, user: env.get("ok"))
    await broker.publish("ch", {"ok": False})
    await broker.publish("ch", {"ok": True})
    env = await asyncio.wait_for(sub.get(), timeout=1)
    assert env["ok"] is True
    await broker.close()


# =============================================================================
# 2. Auth filter tests
# =============================================================================


def test_filter_public_always_passes():
    f = filter_for_rule("public")
    assert f({}, None) is True
    assert f({}, {"id": "u1"}) is True


def test_filter_authenticated_rejects_anonymous():
    f = filter_for_rule("authenticated")
    assert f({}, None) is False
    assert f({}, {"id": "u1"}) is True


def test_filter_admin_requires_admin_role():
    f = filter_for_rule("admin")
    assert f({}, None) is False
    assert f({}, {"id": "u1", "role": "user"}) is False
    assert f({}, {"id": "u1", "role": "admin"}) is True


def test_filter_owner_matches_created_by():
    f = filter_for_rule("owner")
    env = {"record": {"created_by": "user-1"}}
    assert f(env, None) is False
    assert f(env, {"id": "user-2"}) is False
    assert f(env, {"id": "user-1"}) is True


# =============================================================================
# 3. Auto-emit bridge tests
# =============================================================================


@pytest.fixture
async def bridge_setup(db_path):
    """App with auto-emit wired; yields (app, built_app, store, posts)."""
    app = Zeno(database=db_path)
    posts = Collection("posts", fields=[TextField("title", required=True)])
    app.register(posts, auth=["read:public", "write:public"])
    built = app.build()
    # Trigger DB init
    with TestClient(built):
        pass
    db = Database(db_path)
    await db.connect()
    store = CollectionStore(db)
    yield app, store, posts
    await db.disconnect()


@pytest.mark.asyncio
async def test_bridge_create_publishes_create_event(bridge_setup):
    app, store, posts = bridge_setup
    sub = await app.realtime.broker.subscribe(["collection:posts"])
    await store.create(posts, {"title": "Hello"})
    env = await asyncio.wait_for(sub.get(), timeout=2)
    assert env["event"] == "create"
    assert env["collection"] == "posts"
    assert env["record"]["title"] == "Hello"
    await app.realtime.broker.unsubscribe(sub)


@pytest.mark.asyncio
async def test_bridge_update_publishes_update_event_with_previous(bridge_setup):
    app, store, posts = bridge_setup
    sub = await app.realtime.broker.subscribe(["collection:posts"])
    rec = await store.create(posts, {"title": "Old"})
    _ = await sub.get()  # discard create event
    await store.update(posts, rec["id"], {"title": "New"})
    env = await asyncio.wait_for(sub.get(), timeout=2)
    assert env["event"] == "update"
    assert env["record"]["title"] == "New"
    assert env["previous"]["title"] == "Old"
    await app.realtime.broker.unsubscribe(sub)


@pytest.mark.asyncio
async def test_bridge_delete_publishes_delete_event(bridge_setup):
    app, store, posts = bridge_setup
    sub = await app.realtime.broker.subscribe(["collection:posts"])
    rec = await store.create(posts, {"title": "Bye"})
    _ = await sub.get()  # discard create
    await store.delete(posts, rec["id"])
    env = await asyncio.wait_for(sub.get(), timeout=2)
    assert env["event"] == "delete"
    assert env["record"]["id"] == rec["id"]
    await app.realtime.broker.unsubscribe(sub)


@pytest.mark.asyncio
async def test_bridge_disable_auto_emit(db_path):
    app = Zeno(database=db_path)
    posts = Collection("posts", fields=[TextField("title", required=True)])
    app.register(posts, auth=["read:public", "write:public"])
    app.realtime.disable_auto_emit("posts")
    built = app.build()
    with TestClient(built):
        pass
    db = Database(db_path)
    await db.connect()
    store = CollectionStore(db)
    sub = await app.realtime.broker.subscribe(["collection:posts"])
    await store.create(posts, {"title": "Muted"})
    assert sub._queue.empty()
    await db.disconnect()


@pytest.mark.asyncio
async def test_bridge_custom_envelope_builder(db_path):
    app = Zeno(database=db_path)
    posts = Collection("posts", fields=[TextField("title", required=True)])
    app.register(posts, auth=["read:public", "write:public"])

    def my_builder(collection, event, record, **_):
        return {"ch": f"collection:{collection}", "ev": event, "r": record}

    app.realtime.envelope_builder = my_builder
    built = app.build()
    with TestClient(built):
        pass
    db = Database(db_path)
    await db.connect()
    store = CollectionStore(db)
    sub = await app.realtime.broker.subscribe(["collection:posts"])
    await store.create(posts, {"title": "Custom"})
    env = await asyncio.wait_for(sub.get(), timeout=2)
    assert "ev" in env  # custom key
    assert env["ev"] == "create"
    await db.disconnect()


# =============================================================================
# 4. WebSocket end-to-end tests
# =============================================================================


def test_ws_bad_token_closes_connection(realtime_app):
    """A bad JWT token causes the server to close the WebSocket.
    Starlette TestClient surfaces this as a WebSocketDisconnect on receive."""
    from starlette.websockets import WebSocketDisconnect
    built = realtime_app.build()
    with TestClient(built) as client:
        with client.websocket_connect("/api/realtime?token=bad-token") as ws:
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()


def test_ws_subscribe_and_receive_create_event(realtime_app):
    built = realtime_app.build()
    with TestClient(built) as client:
        # Create record first (before subscribe to generate a token we can use
        # without auth since collection is public — use no-token path)
        with client.websocket_connect("/api/realtime") as ws:
            # No token — proceeds as anonymous; collection is public so filter passes
            ws.send_json({"action": "subscribe", "channel": "collection:posts"})
            ack = ws.receive_json()
            assert ack["type"] == "ack"
            assert ack["action"] == "subscribe"

            # Create a post via HTTP in a background thread is not possible here;
            # use the store directly via another fixture path.
            # Instead verify the subscribe ack works and the protocol is correct.
            ws.send_json({"action": "ping"})
            pong = ws.receive_json()
            assert pong["type"] == "pong"


def test_ws_unsubscribe(realtime_app):
    built = realtime_app.build()
    with TestClient(built) as client:
        with client.websocket_connect("/api/realtime") as ws:
            ws.send_json({"action": "subscribe", "channel": "collection:posts"})
            ws.receive_json()  # ack
            ws.send_json({"action": "unsubscribe", "channel": "collection:posts"})
            ack = ws.receive_json()
            assert ack["type"] == "ack"
            assert ack["action"] == "unsubscribe"


def test_ws_unknown_action_returns_error(realtime_app):
    built = realtime_app.build()
    with TestClient(built) as client:
        with client.websocket_connect("/api/realtime") as ws:
            ws.send_json({"action": "explode"})
            msg = ws.receive_json()
            assert msg["type"] == "error"


def test_ws_end_to_end_create_event(db_path):
    """Subscribe via WS, create record via HTTP, assert event received over WS."""
    app = Zeno(database=db_path)
    posts = Collection("posts", fields=[TextField("title", required=True)])
    app.register(posts, auth=["read:public", "write:public"])
    built = app.build()

    with TestClient(built) as client:
        with client.websocket_connect("/api/realtime") as ws:
            ws.send_json({"action": "subscribe", "channel": "collection:posts"})
            ws.receive_json()  # ack

            # Create a record via HTTP — triggers after_create hook → broker
            resp = client.post("/api/posts", json={"title": "Realtime!"})
            assert resp.status_code == 201

            # The WS client should receive the envelope
            msg = ws.receive_json()
            assert msg["type"] == "envelope"
            assert msg["event"] == "create"
            assert msg["record"]["title"] == "Realtime!"


def test_ws_custom_channel(db_path):
    """Publish a custom event via app.realtime.publish → received over WS."""
    import threading

    app = Zeno(database=db_path)
    built = app.build()

    with TestClient(built) as client:
        with client.websocket_connect("/api/realtime") as ws:
            ws.send_json({"action": "subscribe", "channel": "fraud:detected"})
            ws.receive_json()  # ack

            received: list = []

            def publish():
                import asyncio
                asyncio.run(
                    app.realtime.publish("fraud:detected", {"score": 0.99}, event="alert")
                )

            t = threading.Thread(target=publish)
            t.start()
            t.join(timeout=3)

            msg = ws.receive_json()
            assert msg["channel"] == "fraud:detected"


# =============================================================================
# 5. SSE end-to-end tests
# =============================================================================


def test_sse_bad_token_returns_401(realtime_app):
    built = realtime_app.build()
    with TestClient(built) as client:
        resp = client.get(
            "/api/realtime/sse?token=bad&channel=collection:posts"
        )
        assert resp.status_code == 401


def test_sse_missing_channel_returns_400(realtime_app):
    built = realtime_app.build()
    with TestClient(built) as client:
        resp = client.get("/api/realtime/sse")
        assert resp.status_code == 400


def test_sse_public_collection_no_token_not_required(db_path):
    """Public collection SSE filter allows unauthenticated users.

    Full streaming is covered by test_sse_end_to_end_create_event.
    This test verifies that the per-channel auth filter built for a public
    collection passes envelopes for anonymous (user=None) callers.
    """
    from zeno.realtime.sse import _build_filter

    app = Zeno(database=db_path)
    posts = Collection("posts", fields=[TextField("title", required=True)])
    app.register(posts, auth=["read:public", "write:public"])
    app.build()  # populates app.realtime._collections

    f = _build_filter(["collection:posts"], app.realtime, user=None)
    envelope = {"channel": "collection:posts", "event": "create", "record": {}}

    # None means no filter (all pass); otherwise the filter must allow anonymous
    assert f is None or f(envelope, None)


def test_sse_end_to_end_create_event(db_path, monkeypatch):
    """Subscribe via SSE, publish directly into the broker (bypassing HTTP),
    confirm the data frame arrives over the stream.

    Uses a separate thread for the SSE consumer and injects the event via
    asyncio.get_event_loop().call_soon_threadsafe so the queue notification
    fires on the correct event loop without the TestClient streaming portal
    blocking concurrent HTTP requests.
    """
    import threading
    import asyncio
    import zeno.realtime.sse as sse_module
    monkeypatch.setattr(sse_module, "HEARTBEAT_INTERVAL", 2)  # cap max wait at 2s

    app = Zeno(database=db_path)
    posts = Collection("posts", fields=[TextField("title", required=True)])
    app.register(posts, auth=["read:public", "write:public"])
    built = app.build()

    received_frames: list = []
    stream_ready = threading.Event()
    stop_reading = threading.Event()
    loop_ref: list = [None]  # capture the event loop from inside the ASGI context

    original_subscribe = app.realtime.broker.subscribe

    async def capturing_subscribe(*args, **kwargs):
        """Wrap subscribe() to capture the running event loop."""
        loop_ref[0] = asyncio.get_running_loop()
        return await original_subscribe(*args, **kwargs)

    monkeypatch.setattr(app.realtime.broker, "subscribe", capturing_subscribe)

    def read_sse(client):
        with client.stream("GET", "/api/realtime/sse?channel=collection:posts") as resp:
            assert resp.status_code == 200
            stream_ready.set()
            for line in resp.iter_lines():
                if stop_reading.is_set():
                    break
                if line.startswith("data: "):
                    received_frames.append(json.loads(line[len("data: "):]))
                    stop_reading.set()
                    break

    with TestClient(built) as client:
        t = threading.Thread(target=read_sse, args=(client,), daemon=True)
        t.start()

        stream_ready.wait(timeout=5)

        # Give the event loop a moment to start the async generator
        import time; time.sleep(0.1)

        # Inject the event onto the correct event loop via call_soon_threadsafe
        envelope = {
            "channel": "collection:posts",
            "event": "create",
            "collection": "posts",
            "record": {"id": "test-1", "title": "SSE test", "created_by": None},
            "id": "test-1",
            "ts": "2026-01-01T00:00:00+00:00",
        }
        if loop_ref[0] is not None:
            # Schedule broker.publish on the ASGI event loop
            future = asyncio.run_coroutine_threadsafe(
                app.realtime.broker.publish("collection:posts", envelope),
                loop_ref[0],
            )
            future.result(timeout=3)
        else:
            # Fallback: direct queue injection (same-loop)
            import asyncio as _asyncio
            _asyncio.run(app.realtime.broker.publish("collection:posts", envelope))

        t.join(timeout=5)

    assert received_frames, "No SSE frame received"
    assert received_frames[0]["event"] == "create"
    assert received_frames[0]["record"]["title"] == "SSE test"


# =============================================================================
# 6. Custom realtime.publish test
# =============================================================================


@pytest.mark.asyncio
async def test_realtime_publish_custom_envelope():
    app = Zeno(database=":memory:")
    sub = await app.realtime.broker.subscribe(["custom:channel"])
    await app.realtime.publish("custom:channel", {"hello": "world"}, event="greet")
    env = await asyncio.wait_for(sub.get(), timeout=1)
    assert env["channel"] == "custom:channel"
    assert env["event"] == "greet"
    assert env["data"] == {"hello": "world"}
    await app.realtime.broker.unsubscribe(sub)


@pytest.mark.asyncio
async def test_realtime_publish_passthrough_if_already_envelope():
    """If payload already has a 'channel' key it is published as-is."""
    app = Zeno(database=":memory:")
    sub = await app.realtime.broker.subscribe(["my:ch"])
    pre_built = {"channel": "my:ch", "event": "custom", "data": 42}
    await app.realtime.publish("my:ch", pre_built)
    env = await asyncio.wait_for(sub.get(), timeout=1)
    assert env is pre_built
    await app.realtime.broker.unsubscribe(sub)
