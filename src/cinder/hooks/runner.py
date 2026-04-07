from __future__ import annotations

import inspect
from typing import Any

from cinder.hooks.registry import HookRegistry


class HookRunner:
    """Executes handlers registered for an event, in registration order.

    - ``before_*`` handlers mutate the payload by returning a new value.
      Returning ``None`` leaves the payload unchanged.
    - ``after_*`` handlers can return ``None``; return values are still
      propagated for consistency.
    - Sync and async handlers both work; sync returns are awaited if needed.
    - Raising :class:`cinder.errors.CinderError` (including the
      ``cancel_delete`` sentinel) aborts the chain and propagates the error
      so the caller can decide whether to swallow it (soft delete) or bubble
      it to the client.
    """

    def __init__(self, registry: HookRegistry) -> None:
        self.registry = registry

    async def run(self, event: str, payload: Any, ctx: Any) -> Any:
        for handler in self.registry.get(event):
            result = handler(payload, ctx)
            if inspect.isawaitable(result):
                result = await result
            if result is not None:
                payload = result
        return payload

    async def fire(self, event: str, payload: Any, ctx: Any) -> Any:
        return await self.run(event, payload, ctx)
