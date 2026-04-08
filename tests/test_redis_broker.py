"""Tests for RedisBroker using fakeredis.

Verifies pub/sub round-trips, multiple subscribers, filter application,
unsubscribe cleanup, and close() cancels background tasks.
"""
import asyncio
import json
import pytest

from cinder.realtime.broker import BrokerProtocol, RealtimeBroker, Subscription
from cinder.realtime.redis_broker import RedisBroker


# ---------------------------------------------------------------------------
# BrokerProtocol structural compliance
# ---------------------------------------------------------------------------

def test_in_process_broker_satisfies_protocol():
    assert isinstance(RealtimeBroker(), BrokerProtocol)


def test_redis_broker_satisfies_protocol():
    assert isinstance(RedisBroker(), BrokerProtocol)


# ---------------------------------------------------------------------------
# RedisBroker with fakeredis
# ---------------------------------------------------------------------------

@pytest.fixture
async def fake_redis():
    try:
        import fakeredis.aioredis as fakeredis  # type: ignore
    except ImportError:
        pytest.skip("fakeredis not installed")
    r = fakeredis.FakeRedis(decode_responses=False)
    yield r
    await r.aclose()


@pytest.fixture
def broker(fake_redis, monkeypatch):
    async def _get_client():
        return fake_redis

    monkeypatch.setattr("cinder.cache.redis_client.get_client", _get_client)
    monkeypatch.setattr("cinder.realtime.redis_broker.RedisBroker._redis", lambda self: _get_client())
    b = RedisBroker()
    return b


@pytest.mark.asyncio
async def test_publish_subscribe_round_trip(broker, fake_redis):
    sub = await broker.subscribe(["posts"])
    envelope = {"event": "create", "collection": "posts", "record": {"id": 1}}

    await broker.publish("posts", envelope)
    await asyncio.sleep(0.05)  # let the listener task process

    received = await asyncio.wait_for(sub.get(), timeout=1.0)
    assert received == envelope

    await broker.close()


@pytest.mark.asyncio
async def test_multiple_subscribers_all_receive(broker, fake_redis):
    sub1 = await broker.subscribe(["posts"])
    sub2 = await broker.subscribe(["posts"])
    envelope = {"event": "create", "collection": "posts", "record": {"id": 2}}

    await broker.publish("posts", envelope)
    await asyncio.sleep(0.05)

    r1 = await asyncio.wait_for(sub1.get(), timeout=1.0)
    r2 = await asyncio.wait_for(sub2.get(), timeout=1.0)
    assert r1 == envelope
    assert r2 == envelope

    await broker.close()


@pytest.mark.asyncio
async def test_filter_applied(broker, fake_redis):
    """Subscriber with a filter that rejects the envelope should not receive it."""
    def reject_all(envelope, user):
        return False

    sub = await broker.subscribe(["posts"], filter=reject_all)
    envelope = {"event": "create", "collection": "posts", "record": {"id": 3}}
    await broker.publish("posts", envelope)
    await asyncio.sleep(0.05)

    # Queue should be empty — no delivery
    assert sub._queue.empty()
    await broker.close()


@pytest.mark.asyncio
async def test_unsubscribe_closes_queue(broker, fake_redis):
    sub = await broker.subscribe(["posts"])
    assert broker.subscription_count == 1

    await broker.unsubscribe(sub)
    assert broker.subscription_count == 0

    # After close, get() should return None (sentinel)
    result = await asyncio.wait_for(sub.get(), timeout=1.0)
    assert result is None


@pytest.mark.asyncio
async def test_close_cancels_all_tasks(broker, fake_redis):
    await broker.subscribe(["posts"])
    await broker.subscribe(["tags"])
    assert broker.subscription_count == 2

    await broker.close()
    assert broker.subscription_count == 0


@pytest.mark.asyncio
async def test_wrong_channel_not_delivered(broker, fake_redis):
    sub = await broker.subscribe(["tags"])
    envelope = {"event": "create", "collection": "posts", "record": {"id": 5}}
    await broker.publish("posts", envelope)
    await asyncio.sleep(0.05)

    assert sub._queue.empty()
    await broker.close()


@pytest.mark.asyncio
async def test_subscription_count(broker, fake_redis):
    assert broker.subscription_count == 0
    sub = await broker.subscribe(["posts"])
    assert broker.subscription_count == 1
    await broker.unsubscribe(sub)
    assert broker.subscription_count == 0
