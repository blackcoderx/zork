from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from cinder.auth import Auth
from cinder.auth.models import create_auth_tables, cleanup_expired_blocklist
from cinder.auth.routes import build_auth_routes
from cinder.collections.router import build_collection_routes
from cinder.collections.schema import Collection, TextField
from cinder.collections.store import CollectionStore
from cinder.db.connection import Database
from cinder.hooks.context import CinderContext
from cinder.hooks.registry import HookRegistry
from cinder.hooks.runner import HookRunner
from cinder.pipeline import build_middleware_stack
from cinder.realtime import RealtimeFacade
from cinder.realtime.broker import RealtimeBroker

logger = logging.getLogger("cinder")


class _AppHooks:
    """Public facade for app-level hooks — ``app.hooks.on(...)`` / ``app.hooks.fire(...)``.

    Because this wraps the app's *shared* registry, developers can register
    handlers for any event name — built-in (``"posts:before_create"``,
    ``"auth:after_login"``), or fully custom (``"fraud:detected"``,
    ``"app:startup"``). Cross-collection observation and custom event
    buses both work through this one surface.
    """

    def __init__(self, registry: HookRegistry, runner: HookRunner) -> None:
        self._registry = registry
        self._runner = runner

    def on(self, event: str, handler=None):
        if handler is None:
            def decorator(fn):
                self._registry.on(event, fn)
                return fn
            return decorator
        self._registry.on(event, handler)
        return handler

    async def fire(self, event: str, payload, ctx):
        return await self._runner.fire(event, payload, ctx)


class Cinder:
    def __init__(self, database: str = "app.db"):
        self.database = database
        self._collections: dict[str, tuple[Collection, dict[str, str]]] = {}
        self._auth: Auth | None = None
        self._secret: str | None = None
        self._registry: HookRegistry = HookRegistry()
        self._runner: HookRunner = HookRunner(self._registry)
        self.hooks: _AppHooks = _AppHooks(self._registry, self._runner)
        self._broker: RealtimeBroker = RealtimeBroker()
        self.realtime: RealtimeFacade = RealtimeFacade(self._broker, self)

    def on(self, event: str, handler=None):
        """Shorthand for ``app.hooks.on(event, handler)``.

        Works for any event string — built-in or custom — and supports
        both direct and decorator forms.
        """
        return self.hooks.on(event, handler)

    def register(self, collection: Collection, auth: list[str] | None = None) -> None:
        auth_rules = {}
        if auth:
            for rule in auth:
                parts = rule.split(":")
                if len(parts) == 2:
                    auth_rules[parts[0]] = parts[1]

        # Auto-add created_by field if owner rule is used
        if "owner" in auth_rules.values():
            has_created_by = any(f.name == "created_by" for f in collection.fields)
            if not has_created_by:
                collection.fields.append(TextField("created_by"))

        # Bind the collection to the app's shared registry so app-level
        # handlers and collection-level handlers live in one place.
        collection.bind_registry(self._registry, self._runner)
        self._collections[collection.name] = (collection, auth_rules)

    def use_auth(self, auth: Auth) -> None:
        self._auth = auth
        auth.bind_registry(self._registry, self._runner)

    def _get_secret(self) -> str:
        if self._secret:
            return self._secret

        self._secret = os.getenv("CINDER_SECRET")
        if not self._secret:
            self._secret = secrets.token_urlsafe(32)
            logger.warning(
                "No CINDER_SECRET set — tokens will not survive restarts. "
                "Set CINDER_SECRET in your .env file."
            )
        return self._secret

    def build(self) -> Starlette:
        db = Database(self.database)
        store = CollectionStore(db)
        secret = self._get_secret()
        collections = self._collections
        auth = self._auth

        # Track whether the one-time startup initialisation has been performed.
        # Using a mutable container so the nested coroutine can update it.
        _init_done: list[bool] = [False]

        async def _init() -> None:
            if _init_done[0]:
                return
            await db.connect()
            logger.info(f"Connected to database: {self.database}")

            for name, (collection, _) in collections.items():
                await store.sync_schema(collection)
                logger.info(f"Synced collection: {name}")

            if auth:
                extend_cols = auth.get_extend_columns_sql()
                await create_auth_tables(db, extend_cols if extend_cols else None)
                await cleanup_expired_blocklist(db)
                logger.info("Auth tables ready")

            _init_done[0] = True

        app_runner = self._runner

        broker = self._broker

        @asynccontextmanager
        async def lifespan(app: Starlette):
            await _init()
            await app_runner.fire("app:startup", None, CinderContext.system())
            yield
            await app_runner.fire("app:shutdown", None, CinderContext.system())
            await broker.close()
            await db.disconnect()
            logger.info("Database disconnected")

        routes: list[Route] = []

        async def health(request: Request) -> JSONResponse:
            return JSONResponse({"status": "ok"})

        routes.append(Route("/api/health", health, methods=["GET"]))
        routes.extend(build_collection_routes(collections, store))

        if auth:
            routes.extend(build_auth_routes(auth, db, secret))

        # Install the auto-emit bridge and add realtime routes
        self.realtime._install_bridge(self._registry, collections)
        routes.extend(self.realtime._build_routes(db, secret))

        starlette_app = Starlette(routes=routes, lifespan=lifespan)

        # LazyInitMiddleware ensures _init() is called before the first request
        # even when the lifespan is not triggered (e.g. Starlette TestClient
        # used without a context manager).
        class LazyInitMiddleware:
            def __init__(self, inner: ASGIApp) -> None:
                self._inner = inner

            async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
                if scope["type"] in ("http", "websocket") and not _init_done[0]:
                    await _init()
                await self._inner(scope, receive, send)

        wrapped = build_middleware_stack(
            starlette_app,
            db=db if auth else None,
            secret=secret if auth else None,
            hook_runner=self._runner,
        )

        # Wrap *outside* the existing middleware stack so lazy init fires first.
        return LazyInitMiddleware(wrapped)  # type: ignore[return-value]

    def serve(self, host: str = "0.0.0.0", port: int = 8000, reload: bool = False) -> None:
        import uvicorn
        app = self.build()
        uvicorn.run(app, host=host, port=port)
