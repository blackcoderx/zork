from __future__ import annotations

from typing import Callable


class HookRegistry:
    """A simple named-event registry.

    Maps event names (any string) to an ordered list of handlers. Handlers
    execute in registration order. No event name is validated — Cinder's
    built-in lifecycle events and developer-defined custom events share the
    same registry.
    """

    def __init__(self) -> None:
        self._hooks: dict[str, list[Callable]] = {}

    def on(self, event: str, handler: Callable) -> None:
        self._hooks.setdefault(event, []).append(handler)

    def get(self, event: str) -> list[Callable]:
        return self._hooks.get(event, [])

    def clear(self, event: str | None = None) -> None:
        if event is None:
            self._hooks.clear()
        else:
            self._hooks.pop(event, None)
