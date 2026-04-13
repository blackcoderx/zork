from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from cinder.hooks.registry import HookRegistry
from cinder.realtime.broker import RealtimeBroker

logger = logging.getLogger("cinder.realtime.bridge")


def default_envelope(
    collection: str,
    event: str,
    record: dict,
    *,
    previous: dict | None = None,
) -> dict:
    """Build the standard envelope published to the broker.

    Developers can replace this via ``app.realtime.envelope_builder``.

    Shape::

        {
          "channel":    "collection:posts",
          "event":      "create" | "update" | "delete",
          "collection": "posts",
          "record":     { ... },
          "previous":   { ... },   # update/delete only
          "id":         "<record uuid>",
          "ts":         "2026-04-07T12:00:00Z"
        }
    """
    envelope: dict[str, Any] = {
        "channel":    f"collection:{collection}",
        "event":      event,
        "collection": collection,
        "record":     record,
        "id":         record.get("id"),
        "ts":         datetime.now(timezone.utc).isoformat(),
    }
    if previous is not None:
        envelope["previous"] = previous
    return envelope


def install(
    registry: HookRegistry,
    collections: dict,          # {name: (Collection, auth_rules)}
    broker: RealtimeBroker,
    *,
    disabled: set[str],
    envelope_builder: Callable = default_envelope,
) -> None:
    """Register ``after_*`` hook handlers on the shared registry for every
    collection so that CRUD events are automatically published to the broker.

    Called from ``Cinder.build()`` after all collections are bound.
    Handlers are installed directly on the registry (not through the
    collection proxy) so they do not add a ``{collection}:`` prefix twice.
    """
    for name, (collection, _) in collections.items():
        if name in disabled:
            continue

        _install_for_collection(name, registry, broker, envelope_builder)


def _install_for_collection(
    name: str,
    registry: HookRegistry,
    broker: RealtimeBroker,
    builder: Callable,
) -> None:
    channel = f"collection:{name}"

    async def on_after_create(record: dict, ctx) -> None:
        envelope = builder(name, "create", record)
        await broker.publish(channel, envelope)

    async def on_after_update(payload: tuple, ctx) -> None:
        updated, previous = payload
        envelope = builder(name, "update", updated, previous=previous)
        await broker.publish(channel, envelope)

    async def on_after_delete(record: dict, ctx) -> None:
        envelope = builder(name, "delete", record)
        await broker.publish(channel, envelope)

    registry.on(f"{name}:after_create", on_after_create)
    registry.on(f"{name}:after_update", on_after_update)
    registry.on(f"{name}:after_delete", on_after_delete)

    logger.debug("Auto-emit bridge installed for collection '%s'", name)
