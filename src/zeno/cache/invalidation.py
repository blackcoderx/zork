"""Tag-based cache invalidation for Cinder collections.

Wires ``after_create``, ``after_update``, and ``after_delete`` hooks for every
registered collection so that writes automatically bust cached responses.

The invalidation strategy:
- Every cached response for a collection list endpoint is registered under the
  tag set ``tag:collection:{name}`` in the backend.
- On write, all keys in that tag set are deleted atomically, then the tag set
  itself is removed.
- On update/delete, the specific ``get`` key for that record is also deleted.

Usage (called from ``app.py`` during ``build()``)::

    from cinder.cache.invalidation import install_invalidation
    install_invalidation(registry, backend, collections)
"""
from __future__ import annotations

import logging

from cinder.cache.backends import CacheBackend
from cinder.hooks.registry import HookRegistry

logger = logging.getLogger("cinder.cache.invalidation")

TAG_PREFIX = "tag:collection"
CACHE_PREFIX = "response"


def _list_tag(name: str) -> str:
    return f"{TAG_PREFIX}:{name}"


def _get_key(name: str, record_id) -> str:
    return f"{CACHE_PREFIX}:{name}:get:{record_id}"


def install_invalidation(
    registry: HookRegistry,
    backend: CacheBackend,
    collections: dict,
) -> None:
    """Register invalidation hooks for all collections in *collections*."""
    for name in collections:
        _register_hooks(registry, backend, name)


def _register_hooks(
    registry: HookRegistry,
    backend: CacheBackend,
    name: str,
) -> None:
    tag = _list_tag(name)

    async def _invalidate_list(record, ctx):
        """Delete all cached list responses for this collection."""
        try:
            members = await backend.smembers(tag)
            if members:
                await backend.delete(*members)
                logger.debug("Cache invalidated %d list keys for '%s'", len(members), name)
            await backend.sdelete(tag)
        except Exception:
            logger.exception("Cache invalidation failed for collection '%s'", name)

    async def _invalidate_record(record, ctx):
        """Delete the cached get-by-id response for this record."""
        try:
            record_id = record.get("id") if isinstance(record, dict) else None
            if record_id is not None:
                key = _get_key(name, record_id)
                await backend.delete(key)
                logger.debug("Cache invalidated get key for '%s' id=%s", name, record_id)
        except Exception:
            logger.exception("Cache invalidation (get) failed for collection '%s'", name)

    async def after_create(record, ctx):
        await _invalidate_list(record, ctx)

    async def after_update(record, ctx):
        await _invalidate_list(record, ctx)
        await _invalidate_record(record, ctx)

    async def after_delete(record, ctx):
        await _invalidate_list(record, ctx)
        await _invalidate_record(record, ctx)

    registry.on(f"{name}:after_create", after_create)
    registry.on(f"{name}:after_update", after_update)
    registry.on(f"{name}:after_delete", after_delete)
