"""Tests for tag-based cache invalidation."""
import pytest
from cinder.cache.backends import MemoryCacheBackend
from cinder.cache.invalidation import install_invalidation, _list_tag, _get_key
from cinder.hooks.registry import HookRegistry
from cinder.hooks.runner import HookRunner
from cinder.hooks.context import CinderContext


@pytest.fixture
def setup():
    registry = HookRegistry()
    runner = HookRunner(registry)
    backend = MemoryCacheBackend()
    collections = {"posts": None, "tags": None}
    install_invalidation(registry, backend, collections)
    return registry, runner, backend


async def test_after_create_invalidates_list(setup):
    registry, runner, backend = setup

    # Seed a fake list cache key and register it in the tag
    key = "response:posts:list:abc123"
    await backend.set(key, b"cached")
    await backend.sadd(_list_tag("posts"), key)

    ctx = CinderContext.system()
    await runner.fire("posts:after_create", {"id": 1}, ctx)

    # List key should be gone
    assert await backend.get(key) is None
    assert await backend.smembers(_list_tag("posts")) == set()


async def test_after_update_invalidates_list_and_get(setup):
    registry, runner, backend = setup

    list_key = "response:posts:list:xyz"
    get_key = _get_key("posts", 42)
    await backend.set(list_key, b"list")
    await backend.set(get_key, b"get")
    await backend.sadd(_list_tag("posts"), list_key)

    ctx = CinderContext.system()
    await runner.fire("posts:after_update", {"id": 42}, ctx)

    assert await backend.get(list_key) is None
    assert await backend.get(get_key) is None


async def test_after_delete_invalidates_list_and_get(setup):
    registry, runner, backend = setup

    list_key = "response:posts:list:zzz"
    get_key = _get_key("posts", 7)
    await backend.set(list_key, b"l")
    await backend.set(get_key, b"g")
    await backend.sadd(_list_tag("posts"), list_key)

    ctx = CinderContext.system()
    await runner.fire("posts:after_delete", {"id": 7}, ctx)

    assert await backend.get(list_key) is None
    assert await backend.get(get_key) is None


async def test_invalidation_does_not_affect_other_collections(setup):
    registry, runner, backend = setup

    posts_key = "response:posts:list:aaa"
    tags_key = "response:tags:list:bbb"
    await backend.set(posts_key, b"posts")
    await backend.set(tags_key, b"tags")
    await backend.sadd(_list_tag("posts"), posts_key)
    await backend.sadd(_list_tag("tags"), tags_key)

    ctx = CinderContext.system()
    await runner.fire("posts:after_create", {"id": 1}, ctx)

    assert await backend.get(posts_key) is None
    assert await backend.get(tags_key) == b"tags"  # untouched


async def test_invalidation_backend_error_does_not_raise(setup, monkeypatch):
    registry, runner, backend = setup

    async def boom(*args, **kwargs):
        raise RuntimeError("backend down")

    monkeypatch.setattr(backend, "smembers", boom)

    ctx = CinderContext.system()
    # Should not propagate the exception
    await runner.fire("posts:after_create", {"id": 1}, ctx)
