from __future__ import annotations

from typing import Any, Callable

from zeno.collections.schema import Field
from zeno.hooks.registry import HookRegistry
from zeno.hooks.runner import HookRunner


class Auth:
    def __init__(
        self,
        *,
        token_expiry: int = 86400,
        allow_registration: bool = True,
        extend_user: list[Field] | None = None,
    ):
        self.token_expiry = token_expiry
        self.allow_registration = allow_registration
        self.extend_user = extend_user or []
        self._registry: HookRegistry = HookRegistry()
        self._runner: HookRunner = HookRunner(self._registry)

    def bind_registry(self, registry: HookRegistry, runner: HookRunner) -> None:
        """Swap in a shared registry, migrating any existing handlers."""
        if registry is self._registry:
            return
        for event, handlers in self._registry._hooks.items():
            for h in handlers:
                registry.on(event, h)
        self._registry = registry
        self._runner = runner

    def on(self, event: str, handler: Callable | None = None):
        """Register an auth hook. Namespaced as ``auth:{event}``.

        Supports both direct call and decorator forms.
        """
        full = f"auth:{event}"
        if handler is None:

            def decorator(fn: Callable) -> Callable:
                self._registry.on(full, fn)
                return fn

            return decorator
        self._registry.on(full, handler)
        return handler

    async def fire(self, event: str, payload: Any, ctx: Any) -> Any:
        return await self._runner.fire(f"auth:{event}", payload, ctx)

    def get_extend_columns_sql(self) -> list[str]:
        return [f.column_sql() for f in self.extend_user]
