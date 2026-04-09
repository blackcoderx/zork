from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from functools import partial

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from cinder.auth import Auth
from cinder.auth.models import (
    cleanup_expired_blocklist,
    cleanup_expired_verifications,
    create_auth_tables,
)
from cinder.auth.routes import build_auth_routes
from cinder.cache.backends import CacheBackend, MemoryCacheBackend, RedisCacheBackend
from cinder.cache.invalidation import install_invalidation
from cinder.cache.middleware import CacheMiddleware
from cinder.collections.router import build_collection_routes
from cinder.collections.schema import Collection, TextField
from cinder.collections.store import CollectionStore
from cinder.db.connection import Database
from cinder.hooks.context import CinderContext
from cinder.hooks.registry import HookRegistry
from cinder.hooks.runner import HookRunner
from cinder.pipeline import build_middleware_stack
from cinder.ratelimit.backends import (
    MemoryRateLimitBackend,
    RateLimitBackend,
    RedisRateLimitBackend,
)
from cinder.ratelimit.middleware import RateLimitMiddleware, RateLimitRule
from cinder.realtime import RealtimeFacade
from cinder.realtime.broker import RealtimeBroker

logger = logging.getLogger("cinder")


class _CacheConfig:
    """Fluent cache configuration facade — accessible via ``app.cache``."""

    def __init__(self) -> None:
        self._backend: CacheBackend | None = None
        self._enabled: bool | None = None  # None = auto (True when Redis configured)
        self._default_ttl: int = int(os.getenv("CINDER_CACHE_TTL", "300"))
        self._per_user: bool = True
        self._excluded: list[str] = []

    def use(self, backend: CacheBackend) -> "_CacheConfig":
        """Plug in a custom :class:`CacheBackend` implementation."""
        self._backend = backend
        return self

    def configure(
        self, *, default_ttl: int | None = None, per_user: bool | None = None
    ) -> "_CacheConfig":
        if default_ttl is not None:
            self._default_ttl = default_ttl
        if per_user is not None:
            self._per_user = per_user
        return self

    def exclude(self, *paths: str) -> "_CacheConfig":
        """Opt specific path prefixes out of caching."""
        self._excluded.extend(paths)
        return self

    def enable(self, value: bool = True) -> "_CacheConfig":
        self._enabled = value
        return self

    def _is_enabled(self) -> bool:
        if self._enabled is not None:
            return self._enabled
        env = os.getenv("CINDER_CACHE_ENABLED", "").lower()
        if env in ("true", "1", "yes"):
            return True
        if env in ("false", "0", "no"):
            return False
        # Auto: enable if Redis URL is set or a custom backend was provided
        return bool(self._backend or os.getenv("CINDER_REDIS_URL"))

    def _resolve_backend(self) -> CacheBackend:
        if self._backend:
            return self._backend
        redis_url = os.getenv("CINDER_REDIS_URL")
        if redis_url:
            prefix = os.getenv("CINDER_CACHE_PREFIX", "cinder")
            return RedisCacheBackend(prefix=prefix)
        return MemoryCacheBackend()

    def _build_middleware_factory(self):
        """Return a one-arg factory ``(app) -> CacheMiddleware`` for pipeline wiring."""
        backend = self._resolve_backend()
        ttl = self._default_ttl
        per_user = self._per_user
        excluded = list(self._excluded)

        def factory(app):
            return CacheMiddleware(
                app,
                backend,
                default_ttl=ttl,
                per_user=per_user,
                excluded_paths=excluded,
            )

        return factory, backend


class _RateLimitConfig:
    """Fluent rate-limit configuration facade — accessible via ``app.rate_limit``."""

    def __init__(self) -> None:
        self._backend: RateLimitBackend | None = None
        self._enabled: bool | None = None  # None = auto (env var)
        self._rules: list[RateLimitRule] = []
        self._anon_limit, self._anon_window = self._parse_rule(
            os.getenv("CINDER_RATE_LIMIT_ANON", "100/60")
        )
        self._user_limit, self._user_window = self._parse_rule(
            os.getenv("CINDER_RATE_LIMIT_USER", "1000/60")
        )

    @staticmethod
    def _parse_rule(spec: str) -> tuple[int, int]:
        try:
            limit, window = spec.split("/")
            return int(limit), int(window)
        except (ValueError, AttributeError):
            return 100, 60

    def use(self, backend: RateLimitBackend) -> "_RateLimitConfig":
        self._backend = backend
        return self

    def rule(
        self, path_prefix: str, *, limit: int, window: int = 60, scope: str = "ip"
    ) -> "_RateLimitConfig":
        self._rules.append(
            RateLimitRule(path_prefix, limit=limit, window=window, scope=scope)
        )
        return self

    def enable(self, value: bool = True) -> "_RateLimitConfig":
        self._enabled = value
        return self

    def _is_enabled(self) -> bool:
        if self._enabled is not None:
            return self._enabled
        env = os.getenv("CINDER_RATE_LIMIT_ENABLED", "true").lower()
        return env not in ("false", "0", "no")

    def _resolve_backend(self) -> RateLimitBackend:
        if self._backend:
            return self._backend
        redis_url = os.getenv("CINDER_REDIS_URL")
        if redis_url:
            return RedisRateLimitBackend()
        return MemoryRateLimitBackend()

    def _build_middleware_factory(self):
        """Return a one-arg factory ``(app) -> RateLimitMiddleware`` for pipeline wiring."""
        backend = self._resolve_backend()
        rules = list(self._rules)
        anon_limit, anon_window = self._anon_limit, self._anon_window
        user_limit, user_window = self._user_limit, self._user_window

        def factory(app):
            mw = RateLimitMiddleware(
                app,
                backend,
                anon_limit=anon_limit,
                anon_window=anon_window,
                user_limit=user_limit,
                user_window=user_window,
            )
            for rule in rules:
                mw.add_rule(rule)
            return mw

        return factory


async def _safe_send(backend, message) -> None:
    """Fire-and-forget email send. Swallows exceptions so background task
    failures never crash the event loop or leak to the HTTP response."""
    try:
        await backend.send(message)
    except Exception:
        logger.exception("Background email send failed (to=%s)", message.to)


class _EmailConfig:
    """Fluent email configuration facade — accessible via ``app.email``.

    Example::

        from cinder.email import SMTPBackend

        app.email.use(SMTPBackend.sendgrid(api_key=os.getenv("SENDGRID_API_KEY")))
        app.email.configure(
            from_address="no-reply@myapp.com",
            app_name="MyApp",
            base_url="https://myapp.com",
        )
    """

    def __init__(self) -> None:
        self._backend = None
        self._from_address: str = os.getenv("CINDER_EMAIL_FROM", "noreply@localhost")
        self._app_name: str = os.getenv("CINDER_APP_NAME", "Your App")
        self._base_url: str = os.getenv("CINDER_BASE_URL", "http://localhost:8000")
        # Template override callables — each receives a context dict and returns
        # (subject, html_body, text_body). None = use built-in default.
        self._template_password_reset = None
        self._template_verification = None
        self._template_welcome = None

    def use(self, backend) -> "_EmailConfig":
        """Plug in an :class:`~cinder.email.EmailBackend` implementation."""
        self._backend = backend
        return self

    def configure(
        self,
        *,
        from_address: str | None = None,
        app_name: str | None = None,
        base_url: str | None = None,
    ) -> "_EmailConfig":
        """Set sender address, app name, and base URL for generated links."""
        if from_address is not None:
            self._from_address = from_address
        if app_name is not None:
            self._app_name = app_name
        if base_url is not None:
            self._base_url = base_url
        return self

    def on_password_reset(self, fn) -> "_EmailConfig":
        """Override the password-reset email template.

        ``fn`` receives::

            {
                "reset_url":      str,
                "app_name":       str,
                "expiry_minutes": int,
            }

        ``fn`` must return ``(subject: str, html_body: str, text_body: str)``.

        Example::

            def my_reset(ctx):
                url = ctx["reset_url"]
                return (
                    "Reset your password",
                    f"<p><a href='{url}'>Click here</a> to reset.</p>",
                    f"Reset link: {url}",
                )

            app.email.on_password_reset(my_reset)
        """
        self._template_password_reset = fn
        return self

    def on_verification(self, fn) -> "_EmailConfig":
        """Override the email-verification template.

        ``fn`` receives::

            {
                "verify_url": str,
                "app_name":   str,
            }

        ``fn`` must return ``(subject: str, html_body: str, text_body: str)``.
        """
        self._template_verification = fn
        return self

    def on_welcome(self, fn) -> "_EmailConfig":
        """Override the welcome email template.

        ``fn`` receives::

            {
                "user_email": str,
                "app_name":   str,
            }

        ``fn`` must return ``(subject: str, html_body: str, text_body: str)``.
        """
        self._template_welcome = fn
        return self

    # ------------------------------------------------------------------
    # Internal render helpers — called by auth routes
    # ------------------------------------------------------------------

    def _render_password_reset(self, reset_url: str, expiry_minutes: int = 60):
        ctx = {
            "reset_url": reset_url,
            "app_name": self._app_name,
            "expiry_minutes": expiry_minutes,
        }
        if self._template_password_reset:
            return self._template_password_reset(ctx)
        from cinder.email.templates import password_reset_email

        return password_reset_email(reset_url, self._app_name, expiry_minutes)

    def _render_verification(self, verify_url: str):
        ctx = {"verify_url": verify_url, "app_name": self._app_name}
        if self._template_verification:
            return self._template_verification(ctx)
        from cinder.email.templates import email_verification_email

        return email_verification_email(verify_url, self._app_name)

    def _render_welcome(self, user_email: str):
        ctx = {"user_email": user_email, "app_name": self._app_name}
        if self._template_welcome:
            return self._template_welcome(ctx)
        from cinder.email.templates import welcome_email

        return welcome_email(user_email, self._app_name)

    def _resolve_backend(self):
        if self._backend:
            return self._backend
        from cinder.email.backends import ConsoleEmailBackend

        return ConsoleEmailBackend()

    async def send(self, message) -> None:
        """Dispatch ``message`` in the background (non-blocking).

        The sender address is filled in from ``configure(from_address=...)``
        if the message doesn't have one set. Failures are logged and swallowed
        so email errors never break the HTTP response.

        Can also be called directly from hooks for custom transactional emails::

            from cinder.email import EmailMessage

            @app.on("orders:after_create")
            async def send_confirmation(order, ctx):
                await app.email.send(EmailMessage(
                    to=order["email"],
                    subject="Order confirmed",
                    html_body="<p>Your order is confirmed.</p>",
                    text_body="Your order is confirmed.",
                ))
        """
        if not message.from_address:
            message.from_address = self._from_address
        backend = self._resolve_backend()
        asyncio.create_task(_safe_send(backend, message))


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
    def __init__(
        self,
        database: str = "app.db",
        *,
        title: str = "Cinder API",
        version: str = "1.0.0",
    ):
        self.database = database
        self.title = title
        self.version = version
        self._collections: dict[str, tuple[Collection, dict[str, str]]] = {}
        self._auth: Auth | None = None
        self._secret: str | None = None
        self._registry: HookRegistry = HookRegistry()
        self._runner: HookRunner = HookRunner(self._registry)
        self.hooks: _AppHooks = _AppHooks(self._registry, self._runner)
        self._broker: RealtimeBroker = RealtimeBroker()
        self.realtime: RealtimeFacade = RealtimeFacade(self._broker, self)
        # Phase 8 subsystems
        self.cache: _CacheConfig = _CacheConfig()
        self.rate_limit: _RateLimitConfig = _RateLimitConfig()
        # Phase 5: email
        self.email: _EmailConfig = _EmailConfig()
        # Phase 4: file storage
        self._storage_backend = None
        # Multi-DB: optional pre-configured backend (set via configure_database())
        self._db_backend_override = None

    def configure_database(self, backend) -> "Cinder":
        """Plug in a fully pre-configured :class:`~cinder.db.backends.base.DatabaseBackend`.

        Takes precedence over ``CINDER_DATABASE_URL``, ``DATABASE_URL``, and
        the ``database=`` constructor argument.  Use this when you need full
        control over pool size, SSL, timeouts, or a custom driver::

            from cinder.db.backends.postgresql import PostgreSQLBackend

            app.configure_database(
                PostgreSQLBackend(
                    url=os.environ["DATABASE_URL"],
                    min_size=2,
                    max_size=20,
                    ssl="require",
                )
            )

        You can also pass any class that implements the
        :class:`~cinder.db.backends.base.DatabaseBackend` ABC (e.g. a Turso /
        libsql adapter).
        """
        self._db_backend_override = backend
        return self

    def configure_storage(self, backend) -> "Cinder":
        """Set the file storage backend used by all ``FileField`` columns.

        Must be called before ``build()`` if any registered collection has a
        ``FileField``. Raises ``CinderError`` at build time (not request time)
        if a ``FileField`` collection is registered without a storage backend.

        Example::

            from cinder.storage import LocalFileBackend, S3CompatibleBackend

            # Local disk (zero config, dev-friendly)
            app.configure_storage(LocalFileBackend("./uploads"))

            # Cloudflare R2
            app.configure_storage(S3CompatibleBackend.r2(
                account_id="xxx", bucket="my-bucket",
                access_key="xxx", secret_key="xxx",
            ))
        """
        self._storage_backend = backend
        return self

    def configure_redis(self, *, url: str) -> "Cinder":
        """Configure Redis for all subsystems in one call.

        Enables Redis-backed cache, rate-limiting, and realtime broker unless
        the developer has already plugged in custom backends.

        Equivalent to setting ``CINDER_REDIS_URL`` environment variable but
        programmatic, which is useful in tests or when the URL is not known at
        module import time.
        """
        from cinder.cache import redis_client as _rc

        _rc.configure(url=url)
        os.environ["CINDER_REDIS_URL"] = url
        return self

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

    def _resolve_broker(self):
        """Select realtime broker based on CINDER_REALTIME_BROKER env var or Redis URL."""
        broker_type = os.getenv("CINDER_REALTIME_BROKER", "").lower()
        redis_url = os.getenv("CINDER_REDIS_URL")
        if broker_type == "redis" or (broker_type == "" and redis_url):
            try:
                from cinder.realtime.redis_broker import RedisBroker

                logger.info("Using Redis realtime broker")
                return RedisBroker()
            except ImportError:
                logger.warning(
                    "RedisBroker requested but redis not installed — falling back to in-process broker"
                )
        return self._broker

    def build(self) -> Starlette:
        if self._db_backend_override is not None:
            # Developer supplied a fully pre-configured backend — bypass URL resolution.
            db = Database.__new__(Database)
            db.url = self.database
            db._backend = self._db_backend_override
        else:
            db = Database(self.database)
        store = CollectionStore(db)
        secret = self._get_secret()
        collections = self._collections
        auth = self._auth

        # Resolve broker (may swap to RedisBroker if configured)
        broker = self._resolve_broker()
        if broker is not self._broker:
            self._broker = broker
            self.realtime = RealtimeFacade(broker, self)

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
                await cleanup_expired_verifications(db)
                logger.info("Auth tables ready")

            _init_done[0] = True

        app_runner = self._runner

        @asynccontextmanager
        async def lifespan(app: Starlette):
            await _init()
            await app_runner.fire("app:startup", None, CinderContext.system())
            yield
            await app_runner.fire("app:shutdown", None, CinderContext.system())
            await broker.close()
            await db.disconnect()
            logger.info("Database disconnected")
            # Close shared Redis client if one was created
            from cinder.cache import redis_client as _rc

            await _rc.close()

        # Validate: if any collection has a FileField, a storage backend must be set
        from cinder.collections.schema import FileField as _FileField
        from cinder.errors import CinderError as _CinderError

        for name, (col, _) in collections.items():
            if any(isinstance(f, _FileField) for f in col.fields):
                if self._storage_backend is None:
                    raise _CinderError(
                        500,
                        f"Collection '{name}' has a FileField but no storage backend is configured. "
                        "Call app.configure_storage(...) before app.build().",
                    )

        # Install orphan file cleanup hooks
        if self._storage_backend is not None:
            from cinder.storage.cleanup import install_file_cleanup

            install_file_cleanup(self._registry, self._storage_backend, collections)

        routes: list[Route] = []

        async def health(request: Request) -> JSONResponse:
            return JSONResponse({"status": "ok"})

        async def index(request: Request) -> HTMLResponse:
            html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cinder Framework</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --charcoal: #2A2A2A;
            --white: #F9F9F9;
            --blazing-orange: #FF5A00;
        }
        body {
            margin: 0;
            padding: 0;
            font-family: 'JetBrains Mono', monospace;
            background-color: var(--white);
            color: var(--charcoal);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            border: 16px solid var(--charcoal);
            box-sizing: border-box;
            position: relative;
            overflow: hidden;
        }
        body::before {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background-image:
                linear-gradient(var(--charcoal) 2px, transparent 2px),
                linear-gradient(90deg, var(--charcoal) 2px, transparent 2px);
            background-size: 60px 60px;
            opacity: 0.06;
            animation: pan 20s linear infinite;
            z-index: -1;
        }
        @keyframes pan {
            0% { transform: translate(0, 0); }
            100% { transform: translate(60px, 60px); }
        }
        .container {
            text-align: center;
            padding: 4rem 3rem;
            position: relative;
            max-width: 90vw;
        }
        h1 {
            font-size: clamp(4rem, 10vw, 8rem);
            font-weight: 800;
            margin: 0 0 0.5rem 0;
            text-transform: uppercase;
            letter-spacing: -4px;
            line-height: 1;
        }
        p {
            font-size: 1.25rem;
            font-weight: 700;
            margin-bottom: 3rem;
            max-width: 500px;
            margin-left: auto;
            margin-right: auto;
            line-height: 1.6;
        }
        .status {
            display: inline-flex;
            align-items: center;
            gap: 0.75rem;
            padding: 1rem 2rem;
            border: 2px solid var(--charcoal);
            background: var(--white);
            font-weight: 800;
            font-size: 1.25rem;
            text-transform: uppercase;
            box-shadow: 8px 8px 0 var(--charcoal);
            transition: all 0.2s ease;
            cursor: default;
        }
        .status:hover {
            transform: translate(-3px, -3px);
            box-shadow: 3px 3px 0 var(--charcoal);
        }
        .status-dot {
            width: 16px;
            height: 16px;
            background-color: var(--blazing-orange);
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(255, 90, 0, 0.8); }
            70% { box-shadow: 0 0 0 12px rgba(255, 90, 0, 0); }
            100% { box-shadow: 0 0 0 0 rgba(255, 90, 0, 0); }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Cinder</h1>
        <p>Your blazing fast Python backend is up and running.</p>
        <div class="status">
            <div class="status-dot"></div>
            Status: OK
        </div>
    </div>
</body>
</html>"""
            return HTMLResponse(html_content)

        routes.append(Route("/", index, methods=["GET"]))
        routes.append(Route("/api/health", health, methods=["GET"]))
        routes.extend(
            build_collection_routes(
                collections, store, storage_backend=self._storage_backend
            )
        )

        if auth:
            routes.extend(build_auth_routes(auth, db, secret, email_config=self.email))

        # Install the auto-emit bridge and add realtime routes
        self.realtime._install_bridge(self._registry, collections)
        routes.extend(self.realtime._build_routes(db, secret))

        # Add OpenAPI/Swagger routes
        from cinder.openapi import CinderOpenAPI

        openapi = CinderOpenAPI(
            title=self.title,
            version=self.version,
            collections=collections,
            auth_enabled=auth is not None,
        )
        routes.extend(openapi.build_routes())

        starlette_app = Starlette(routes=routes, lifespan=lifespan)

        # Build cache & rate-limit middleware factories (None = disabled)
        cache_factory = None
        cache_backend = None
        if self.cache._is_enabled():
            cache_factory, cache_backend = self.cache._build_middleware_factory()
            install_invalidation(self._registry, cache_backend, collections)
            logger.info("Cache enabled (backend: %s)", type(cache_backend).__name__)

        rl_factory = None
        if self.rate_limit._is_enabled():
            rl_factory = self.rate_limit._build_middleware_factory()
            logger.info("Rate limiting enabled")

        # LazyInitMiddleware ensures _init() is called before the first request
        # even when the lifespan is not triggered (e.g. Starlette TestClient
        # used without a context manager).
        class LazyInitMiddleware:
            def __init__(self, inner: ASGIApp) -> None:
                self._inner = inner

            async def __call__(
                self, scope: Scope, receive: Receive, send: Send
            ) -> None:
                if scope["type"] in ("http", "websocket") and not _init_done[0]:
                    await _init()
                await self._inner(scope, receive, send)

        wrapped = build_middleware_stack(
            starlette_app,
            db=db if auth else None,
            secret=secret if auth else None,
            hook_runner=self._runner,
            cache_middleware=cache_factory,
            ratelimit_middleware=rl_factory,
        )

        # Wrap *outside* the existing middleware stack so lazy init fires first.
        return LazyInitMiddleware(wrapped)  # type: ignore[return-value]

    def serve(
        self, host: str = "0.0.0.0", port: int = 8000, reload: bool = False
    ) -> None:
        import uvicorn

        app = self.build()
        uvicorn.run(app, host=host, port=port)
