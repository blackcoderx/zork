from __future__ import annotations

import asyncio
import logging
from typing import Callable, Protocol, runtime_checkable

logger = logging.getLogger("cinder.realtime.broker")


@runtime_checkable
class BrokerProtocol(Protocol):
    """Interface that all Cinder realtime brokers must satisfy.

    Both :class:`RealtimeBroker` (in-process) and ``RedisBroker`` (Redis
    pub/sub) implement this protocol.  Custom brokers should also satisfy it
    so type-checkers can verify drop-in compatibility.
    """

    async def subscribe(
        self,
        channels: list[str],
        *,
        user: dict | None = None,
        filter: Callable[[dict, dict | None], bool] | None = None,
    ) -> "Subscription": ...

    async def unsubscribe(self, subscription: "Subscription") -> None: ...

    async def publish(self, channel: str, envelope: dict) -> None: ...

    async def close(self) -> None: ...

    @property
    def subscription_count(self) -> int: ...


class Subscription:
    """A single subscriber's view of the broker.

    Holds a private ``asyncio.Queue`` that the broker fills with envelopes.
    Iterate with ``async for envelope in subscription`` or pull one at a time
    with ``await subscription.get()``.  Call ``aclose()`` to unsubscribe and
    unblock any waiting ``get()``/``__aiter__`` calls.
    """

    _SENTINEL = object()

    def __init__(
        self,
        channels: list[str],
        *,
        user: dict | None = None,
        filter: Callable[[dict, dict | None], bool] | None = None,
        queue_size: int = 100,
    ) -> None:
        self.channels = list(channels)
        self.user = user
        self.filter = filter
        self.dropped: int = 0
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self._closed: bool = False

    # ------------------------------------------------------------------
    # Internal helpers used by the broker
    # ------------------------------------------------------------------

    def _deliver(self, envelope: dict) -> None:
        """Push an envelope to the queue.

        If the subscriber's filter rejects the envelope, it is silently
        dropped.  If the queue is full, the *oldest* pending item is
        discarded and the new envelope is placed at the back.  This keeps
        slow clients from blocking the broker.
        """
        if self._closed:
            return
        if self.filter is not None and not self.filter(envelope, self.user):
            return
        if self._queue.full():
            try:
                self._queue.get_nowait()  # discard oldest
            except asyncio.QueueEmpty:
                pass
            self.dropped += 1
            logger.warning(
                "Subscription queue full — dropped oldest envelope (total dropped: %d)",
                self.dropped,
            )
        try:
            self._queue.put_nowait(envelope)
        except asyncio.QueueFull:
            self.dropped += 1

    def _close_queue(self) -> None:
        self._closed = True
        try:
            self._queue.put_nowait(self._SENTINEL)
        except asyncio.QueueFull:
            pass

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def get(self) -> dict | None:
        """Wait for the next envelope.  Returns ``None`` when closed."""
        item = await self._queue.get()
        if item is self._SENTINEL:
            return None
        return item  # type: ignore[return-value]

    async def aclose(self) -> None:
        """Unsubscribe and unblock any waiting consumers."""
        self._close_queue()

    def __aiter__(self):
        return self

    async def __anext__(self) -> dict:
        item = await self.get()
        if item is None:
            raise StopAsyncIteration
        return item


class RealtimeBroker:
    """In-process fan-out pub/sub broker.

    Channels are arbitrary strings — any string is valid.  One
    :class:`Subscription` is created per connected client.  Publishers call
    :meth:`publish`; the broker fans out to all subscribers whose channel
    list contains the published channel.

    This broker is intentionally *in-process only*.  A Redis-backed drop-in
    replacement will arrive in Phase 8; the interface is kept minimal so
    swapping is trivial.
    """

    def __init__(self, *, queue_size: int = 100) -> None:
        self._queue_size = queue_size
        self._subscriptions: list[Subscription] = []
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        channels: list[str],
        *,
        user: dict | None = None,
        filter: Callable[[dict, dict | None], bool] | None = None,
    ) -> Subscription:
        """Create and register a new subscription for one or more channels."""
        sub = Subscription(
            channels,
            user=user,
            filter=filter,
            queue_size=self._queue_size,
        )
        async with self._lock:
            self._subscriptions.append(sub)
        return sub

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a subscription and close its queue."""
        async with self._lock:
            try:
                self._subscriptions.remove(subscription)
            except ValueError:
                pass
        await subscription.aclose()

    async def publish(self, channel: str, envelope: dict) -> None:
        """Fan out *envelope* to every subscriber listening on *channel*."""
        async with self._lock:
            targets = [s for s in self._subscriptions if channel in s.channels]
        for sub in targets:
            sub._deliver(envelope)

    async def close(self) -> None:
        """Close all subscriptions.  Called during ``app:shutdown``."""
        async with self._lock:
            targets = list(self._subscriptions)
            self._subscriptions.clear()
        for sub in targets:
            sub._close_queue()

    @property
    def subscription_count(self) -> int:
        return len(self._subscriptions)
