"""Redis pub/sub broker for Cinder realtime.

A drop-in replacement for :class:`~cinder.realtime.broker.RealtimeBroker` that
fans out events across multiple processes/nodes via Redis pub/sub.

Architecture
------------
- ``publish(channel, envelope)`` publishes the JSON-serialised envelope to the
  Redis channel using ``PUBLISH``.
- ``subscribe(channels, ...)`` creates a local :class:`Subscription` (reused
  from the in-process broker) and spawns an ``asyncio`` background task that
  runs a ``PubSub.listen()`` loop, deserialises incoming messages, applies the
  subscriber's ``filter`` callable (RBAC via ``auth_filter.filter_for_rule``),
  and feeds matching envelopes into the subscription's queue.
- RBAC filtering is applied **locally** (after receiving from Redis) so the
  guarantee that subscribers only see records they can read is fully preserved
  even in a multi-process setup.
- ``close()`` cancels all background tasks and closes the pub/sub connections.

Usage::

    from cinder.realtime.redis_broker import RedisBroker
    broker = RedisBroker()
    # In app.py: self._broker = RedisBroker() when CINDER_REALTIME_BROKER=redis
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

from cinder.realtime.broker import Subscription

logger = logging.getLogger("cinder.realtime.redis_broker")


class RedisBroker:
    """Redis pub/sub broker satisfying :class:`~cinder.realtime.broker.BrokerProtocol`."""

    def __init__(self, *, queue_size: int = 100) -> None:
        self._queue_size = queue_size
        self._subscriptions: list[tuple[Subscription, asyncio.Task]] = []
        self._lock = asyncio.Lock()

    async def _redis(self):
        from cinder.cache.redis_client import get_client
        return await get_client()

    async def subscribe(
        self,
        channels: list[str],
        *,
        user: dict | None = None,
        filter: Callable[[dict, dict | None], bool] | None = None,
    ) -> Subscription:
        """Create a new subscription backed by Redis pub/sub."""
        try:
            import redis.asyncio as aioredis  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "Redis not installed. Install with: pip install 'cinder[redis]'"
            ) from exc

        sub = Subscription(
            channels,
            user=user,
            filter=filter,
            queue_size=self._queue_size,
        )

        r = await self._redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(*channels)

        task = asyncio.create_task(
            self._listen(pubsub, sub, channels),
            name=f"redis_broker:listen:{','.join(channels)}",
        )
        task.add_done_callback(self._on_task_done)

        async with self._lock:
            self._subscriptions.append((sub, task))

        return sub

    async def _listen(self, pubsub, sub: Subscription, channels: list[str]) -> None:
        """Background task: pull messages from Redis and deliver to the subscription."""
        try:
            async for message in pubsub.listen():
                if sub._closed:
                    break
                if message["type"] != "message":
                    continue
                try:
                    envelope = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Redis broker: invalid JSON in message, skipping")
                    continue
                sub._deliver(envelope)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Redis broker listen loop error")
        finally:
            try:
                await pubsub.unsubscribe(*channels)
                await pubsub.aclose()
            except Exception:
                pass

    def _on_task_done(self, task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception():
            logger.error("Redis broker task failed: %s", task.exception())

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a subscription, cancel its listener task, and close its queue."""
        async with self._lock:
            for i, (sub, task) in enumerate(self._subscriptions):
                if sub is subscription:
                    self._subscriptions.pop(i)
                    task.cancel()
                    break
        await subscription.aclose()

    async def publish(self, channel: str, envelope: dict) -> None:
        """Publish *envelope* to the Redis channel."""
        r = await self._redis()
        try:
            await r.publish(channel, json.dumps(envelope))
        except Exception:
            logger.exception("Redis broker publish error on channel '%s'", channel)

    async def close(self) -> None:
        """Cancel all listener tasks and close all subscriptions."""
        async with self._lock:
            items = list(self._subscriptions)
            self._subscriptions.clear()

        for sub, task in items:
            task.cancel()
            sub._close_queue()

        # Allow cancelled tasks to complete
        if items:
            await asyncio.gather(*(task for _, task in items), return_exceptions=True)

    @property
    def subscription_count(self) -> int:
        return len(self._subscriptions)
