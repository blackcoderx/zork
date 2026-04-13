from __future__ import annotations

from typing import Callable


def filter_for_rule(rule: str) -> Callable[[dict, dict | None], bool]:
    """Return a filter callable that mirrors the collection's ``read`` auth rule.

    The filter is called per-envelope per-subscriber when the broker fans out
    an event:  ``filter(envelope, user) -> bool``.  Returning ``True`` means
    the envelope is delivered; ``False`` means it is silently dropped for that
    subscriber.

    Rules mirror ``src/cinder/collections/router.py::_check_auth`` /
    ``_check_owner`` exactly so that subscribers only receive events for
    records they are authorised to read via the REST API.

    Developers can always bypass this by passing their own ``filter`` callable
    when subscribing through ``broker.subscribe(...)`` directly.
    """
    if rule == "public":
        return _public_filter

    if rule == "authenticated":
        return _authenticated_filter

    if rule == "admin":
        return _admin_filter

    if rule == "owner":
        return _owner_filter

    # Unknown rule — treat as authenticated (safe default)
    return _authenticated_filter


# ---------------------------------------------------------------------------
# Filter implementations
# ---------------------------------------------------------------------------

def _public_filter(envelope: dict, user: dict | None) -> bool:  # noqa: ARG001
    return True


def _authenticated_filter(envelope: dict, user: dict | None) -> bool:  # noqa: ARG001
    return user is not None


def _admin_filter(envelope: dict, user: dict | None) -> bool:  # noqa: ARG001
    return user is not None and user.get("role") == "admin"


def _owner_filter(envelope: dict, user: dict | None) -> bool:
    if user is None:
        return False
    record = envelope.get("record") or {}
    return record.get("created_by") == user.get("id")
