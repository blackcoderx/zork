import pytest

from zeno.app import Zeno
from zeno.collections.schema import Collection, TextField, IntField
from zeno.collections.store import CollectionStore
from zeno.db.connection import Database
from zeno.errors import ZenoError
from zeno.hooks import ZenoContext, HookRegistry, HookRunner


# ---------- Registry + Runner unit tests ----------


def test_registry_appends_in_order():
    r = HookRegistry()
    a = lambda p, c: p
    b = lambda p, c: p
    r.on("e", a)
    r.on("e", b)
    assert r.get("e") == [a, b]
    assert r.get("unknown") == []


@pytest.mark.asyncio
async def test_runner_mutates_payload_on_return():
    r = HookRegistry()
    runner = HookRunner(r)

    async def h1(p, c):
        return p + 1

    def h2(p, c):
        return p * 2  # sync handler

    def h3(p, c):
        return None  # leaves payload unchanged

    r.on("e", h1)
    r.on("e", h2)
    r.on("e", h3)
    result = await runner.run("e", 1, None)
    assert result == 4  # (1+1)*2


@pytest.mark.asyncio
async def test_runner_propagates_zeno_error():
    r = HookRegistry()
    runner = HookRunner(r)

    def boom(p, c):
        raise ZenoError(403, "nope")

    r.on("e", boom)
    with pytest.raises(ZenoError):
        await runner.run("e", {}, None)


@pytest.mark.asyncio
async def test_runner_empty_event_is_noop():
    r = HookRegistry()
    runner = HookRunner(r)
    assert await runner.fire("nothing", "payload", None) == "payload"


# ---------- Collection lifecycle hooks ----------


@pytest.fixture
async def store_with_posts(db_path):
    db = Database(db_path)
    await db.connect()
    store = CollectionStore(db)
    posts = Collection("posts", fields=[
        TextField("title", required=True),
        TextField("slug"),
        IntField("views", default=0),
    ])
    await store.sync_schema(posts)
    yield store, posts
    await db.disconnect()


@pytest.mark.asyncio
async def test_before_create_mutates_payload(store_with_posts):
    store, posts = store_with_posts

    async def add_slug(data, ctx):
        data["slug"] = data["title"].lower().replace(" ", "-")
        return data

    posts.on("before_create", add_slug)
    rec = await store.create(posts, {"title": "Hello World"})
    assert rec["slug"] == "hello-world"


@pytest.mark.asyncio
async def test_after_create_fires_with_saved_record(store_with_posts):
    store, posts = store_with_posts
    seen = []

    async def on_created(record, ctx):
        seen.append(record)

    posts.on("after_create", on_created)
    rec = await store.create(posts, {"title": "T"})
    assert len(seen) == 1
    assert seen[0]["id"] == rec["id"]


@pytest.mark.asyncio
async def test_after_update_receives_new_prev_tuple(store_with_posts):
    store, posts = store_with_posts
    captured = {}

    async def on_upd(payload, ctx):
        new, prev = payload
        captured["new"] = new
        captured["prev"] = prev

    posts.on("after_update", on_upd)
    rec = await store.create(posts, {"title": "Old"})
    await store.update(posts, rec["id"], {"title": "New"})
    assert captured["prev"]["title"] == "Old"
    assert captured["new"]["title"] == "New"


@pytest.mark.asyncio
async def test_before_delete_cancel_delete_soft_deletes(store_with_posts):
    store, posts = store_with_posts

    def cancel(record, ctx):
        raise ZenoError.cancel_delete()

    after_fired = []
    posts.on("before_delete", cancel)
    posts.on("after_delete", lambda r, c: after_fired.append(r))

    rec = await store.create(posts, {"title": "Pinned"})
    result = await store.delete(posts, rec["id"])
    assert result is True
    # Still in DB
    assert await store._raw_get(posts, rec["id"]) is not None
    # after_delete must NOT have fired
    assert after_fired == []


@pytest.mark.asyncio
async def test_before_create_zeno_error_aborts(store_with_posts):
    store, posts = store_with_posts

    def veto(data, ctx):
        raise ZenoError(403, "no")

    posts.on("before_create", veto)
    with pytest.raises(ZenoError):
        await store.create(posts, {"title": "X"})
    items, total = await store.list(posts)
    assert total == 0


@pytest.mark.asyncio
async def test_before_list_can_mutate_filters(store_with_posts):
    store, posts = store_with_posts
    await store.create(posts, {"title": "A", "views": 0})
    await store.create(posts, {"title": "B", "views": 10})

    def force_filter(query, ctx):
        query["filters"]["views"] = 10
        return query

    posts.on("before_list", force_filter)
    items, total = await store.list(posts)
    assert total == 1
    assert items[0]["title"] == "B"


@pytest.mark.asyncio
async def test_custom_collection_event(store_with_posts):
    store, posts = store_with_posts
    received = []

    posts.on("payment_confirmed", lambda payload, ctx: received.append(payload))
    await posts.fire("payment_confirmed", {"id": 1}, ZenoContext.system())
    assert received == [{"id": 1}]


@pytest.mark.asyncio
async def test_fire_with_no_handlers_is_noop(store_with_posts):
    _, posts = store_with_posts
    # should not raise
    await posts.fire("unregistered_event", "payload", ZenoContext.system())


# ---------- App-level hooks ----------


@pytest.mark.asyncio
async def test_app_hooks_on_and_fire():
    app = Zeno(database=":memory:")
    calls = []
    app.hooks.on("fraud:detected", lambda p, c: calls.append(p))
    await app.hooks.fire("fraud:detected", {"score": 0.95}, ZenoContext.system())
    assert calls == [{"score": 0.95}]


def test_app_startup_fires_via_testclient(tmp_path):
    from starlette.testclient import TestClient

    app = Zeno(database=str(tmp_path / "t.db"))
    startup_calls = []
    shutdown_calls = []
    app.hooks.on("app:startup", lambda p, c: startup_calls.append(1))
    app.hooks.on("app:shutdown", lambda p, c: shutdown_calls.append(1))

    built = app.build()
    with TestClient(built) as client:
        client.get("/api/health")
    assert startup_calls == [1]
    assert shutdown_calls == [1]


# ---------- Auth hooks ----------


@pytest.mark.asyncio
async def test_app_level_handler_fires_collection_event(tmp_path):
    """app.hooks.on('posts:before_create', ...) must fire when store.create
    runs — proving registries are unified, not fragmented per collection."""
    from starlette.testclient import TestClient

    app = Zeno(database=str(tmp_path / "u.db"))
    posts = Collection("posts", fields=[TextField("title", required=True)])
    app.register(posts)

    seen = []
    app.hooks.on("posts:before_create", lambda d, c: seen.append(d) or d)

    built = app.build()
    with TestClient(built) as client:
        resp = client.post("/api/posts", json={"title": "X"})
        assert resp.status_code == 201
    assert len(seen) == 1 and seen[0]["title"] == "X"


@pytest.mark.asyncio
async def test_pre_registered_handlers_migrate_on_bind(tmp_path):
    """Handlers registered on a Collection BEFORE app.register() must still
    fire after the registry is swapped to the app's shared one."""
    posts = Collection("posts", fields=[TextField("title", required=True)])
    calls = []
    posts.on("before_create", lambda d, c: calls.append(d) or d)

    app = Zeno(database=str(tmp_path / "m.db"))
    app.register(posts)  # triggers bind_registry — must migrate the handler

    db = Database(str(tmp_path / "m.db"))
    await db.connect()
    store = CollectionStore(db)
    await store.sync_schema(posts)
    await store.create(posts, {"title": "hi"})
    await db.disconnect()
    assert len(calls) == 1


def test_decorator_form_on_collection():
    posts = Collection("posts", fields=[TextField("title")])

    @posts.on("before_create")
    def h(data, ctx):
        return data

    assert posts._registry.get("posts:before_create") == [h]


@pytest.mark.asyncio
async def test_zeno_on_shorthand():
    app = Zeno(database=":memory:")
    calls = []

    @app.on("fraud:detected")
    def h(p, c):
        calls.append(p)

    await app.hooks.fire("fraud:detected", {"x": 1}, ZenoContext.system())
    assert calls == [{"x": 1}]


def test_app_error_hook_fires_on_unhandled_exception(tmp_path):
    from starlette.testclient import TestClient
    from zeno.collections.schema import Collection, TextField

    app = Zeno(database=str(tmp_path / "err.db"))
    seen = []
    app.hooks.on("app:error", lambda exc, ctx: seen.append(type(exc).__name__))

    # Use the public API: register a collection with a before_create hook
    # that raises a bare RuntimeError.  This exercises the error middleware
    # without touching any private attribute or middleware internals.
    posts = Collection("posts", fields=[TextField("title")])
    app.register(posts, auth=["read:public", "write:public"])

    @posts.on("before_create")
    async def boom(data, ctx):
        raise RuntimeError("kaboom")

    built = app.build()
    with TestClient(built, raise_server_exceptions=False) as client:
        resp = client.post("/api/posts", json={"title": "x"})
        assert resp.status_code == 500
    assert seen == ["RuntimeError"]


@pytest.mark.asyncio
async def test_auth_register_fires_before_and_after(tmp_path):
    from starlette.testclient import TestClient
    from zeno.auth import Auth

    app = Zeno(database=str(tmp_path / "auth.db"))
    auth = Auth()
    before = []
    after = []
    auth.on("before_register", lambda body, ctx: before.append(dict(body)) or body)
    auth.on("after_register", lambda user, ctx: after.append(user))
    app.use_auth(auth)

    built = app.build()
    with TestClient(built) as client:
        resp = client.post(
            "/api/auth/register",
            json={"email": "a@b.com", "password": "secretpw"},
        )
        assert resp.status_code == 201
    assert before and before[0]["email"] == "a@b.com"
    assert after and after[0]["email"] == "a@b.com"
    assert "password" not in after[0]
