from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from zork.auth import Auth
from zork.auth.models import (
    cleanup_expired_blocklist,
    cleanup_expired_refresh_tokens,
    cleanup_expired_verifications,
    create_auth_tables,
)
from zork.auth.routes import build_auth_routes
from zork.cache.backends import CacheBackend, MemoryCacheBackend, RedisCacheBackend
from zork.cache.invalidation import install_invalidation
from zork.cache.middleware import CacheMiddleware
from zork.collections.router import build_collection_routes
from zork.collections.schema import Collection, TextField
from zork.collections.store import CollectionStore
from zork.db.connection import Database
from zork.hooks.context import ZorkContext
from zork.hooks.registry import HookRegistry
from zork.hooks.runner import HookRunner
from zork.pipeline import build_middleware_stack
from zork.ratelimit.backends import (
    MemoryRateLimitBackend,
    RateLimitBackend,
    RedisRateLimitBackend,
)
from zork.ratelimit.middleware import RateLimitMiddleware, RateLimitRule
from zork.realtime import RealtimeFacade
from zork.realtime.broker import RealtimeBroker
from zork.logging import configure_from_env
from zork.staticfiles import StaticFilesConfig, mount_static_files

logger = logging.getLogger("zork")


class _CacheConfig:
    """Fluent cache configuration facade — accessible via ``app.cache``."""

    def __init__(self) -> None:
        self._backend: CacheBackend | None = None
        self._enabled: bool | None = None  # None = auto (True when Redis configured)
        self._default_ttl: int = int(os.getenv("ZORK_CACHE_TTL", "300"))
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
        env = os.getenv("ZORK_CACHE_ENABLED", "").lower()
        if env in ("true", "1", "yes"):
            return True
        if env in ("false", "0", "no"):
            return False
        # Auto: enable if Redis URL is set or a custom backend was provided
        return bool(self._backend or os.getenv("ZORK_REDIS_URL"))

    def _resolve_backend(self) -> CacheBackend:
        if self._backend:
            return self._backend
        redis_url = os.getenv("ZORK_REDIS_URL")
        if redis_url:
            prefix = os.getenv("ZORK_CACHE_PREFIX", "zork")
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
            os.getenv("ZORK_RATE_LIMIT_ANON", "100/60")
        )
        self._user_limit, self._user_window = self._parse_rule(
            os.getenv("ZORK_RATE_LIMIT_USER", "1000/60")
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

    def auth_limits(self) -> "_RateLimitConfig":
        """Set default limits appropriate for authentication endpoints.

        Applies stricter rate limits to login, register, and password reset
        endpoints to protect against brute-force attacks and account enumeration.

        This is optional - call it to enable stricter limits, or use app.rate_limit.rule()
        to customize specific endpoints.

        Limits applied:
        - /api/auth/login: 5 requests/minute per IP
        - /api/auth/register: 3 requests/minute per IP
        - /api/auth/forgot-password: 3 requests/hour per IP+email combination
        """
        self.rule("/api/auth/login", limit=5, window=60, scope="ip")
        self.rule("/api/auth/register", limit=3, window=60, scope="ip")
        self.rule("/api/auth/forgot-password", limit=3, window=3600, scope="both")
        return self

    def enable(self, value: bool = True) -> "_RateLimitConfig":
        self._enabled = value
        return self

    def _is_enabled(self) -> bool:
        if self._enabled is not None:
            return self._enabled
        env = os.getenv("ZORK_RATE_LIMIT_ENABLED", "true").lower()
        return env not in ("false", "0", "no")

    def _resolve_backend(self) -> RateLimitBackend:
        if self._backend:
            return self._backend
        redis_url = os.getenv("ZORK_REDIS_URL")
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


class _CORSConfig:
    """CORS configuration facade — accessible via ``app.cors``.

    By default, CORS is disabled (secure). Configure origins to enable.

    Example::

        app = Zork(database="app.db")
        app.cors.allow_origins(["https://myapp.com"])
        app.cors.allow_methods(["GET", "POST"])
    """

    def __init__(self) -> None:
        self._allow_origins: list[str] = []
        self._allow_credentials: bool = False
        self._allow_methods: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE"]
        self._allow_headers: list[str] = []
        self._expose_headers: list[str] = []
        self._max_age: int | None = None

    def allow_origins(self, origins: list[str]) -> "_CORSConfig":
        """Set allowed origins.

        Use ``["*"]`` to allow all origins (INSECURE with credentials).
        Default: ``[]`` (no CORS).
        """
        self._allow_origins = origins
        return self

    def allow_credentials(self, allow: bool = True) -> "_CORSConfig":
        """Allow credentials (cookies, auth headers).

        When True, origins cannot be ``["*"]``. Default: False.
        """
        self._allow_credentials = allow
        return self

    def allow_methods(self, methods: list[str]) -> "_CORSConfig":
        """Set allowed HTTP methods. Default: GET, POST, PUT, PATCH, DELETE."""
        self._allow_methods = methods
        return self

    def allow_headers(self, headers: list[str]) -> "_CORSConfig":
        """Set allowed request headers. Default: [] (allow all)."""
        self._allow_headers = headers
        return self

    def expose_headers(self, headers: list[str]) -> "_CORSConfig":
        """Set response headers exposed to the client."""
        self._expose_headers = headers
        return self

    def max_age(self, seconds: int) -> "_CORSConfig":
        """Set preflight cache duration in seconds."""
        self._max_age = seconds
        return self

    def _is_configured(self) -> bool:
        """Check if CORS has been configured."""
        return bool(self._allow_origins)

    def _build_config(self) -> dict:
        """Build CORS config dict for pipeline."""
        return {
            "allow_origins": self._allow_origins,
            "allow_credentials": self._allow_credentials,
            "allow_methods": self._allow_methods,
            "allow_headers": self._allow_headers,
            "expose_headers": self._expose_headers,
            "max_age": self._max_age,
        }


class _EmailConfig:
    """Fluent email configuration facade — accessible via ``app.email``.

    Example::

        from zork.email import SMTPBackend

        app.email.use(SMTPBackend.sendgrid(api_key=os.getenv("SENDGRID_API_KEY")))
        app.email.configure(
            from_address="no-reply@myapp.com",
            app_name="MyApp",
            base_url="https://myapp.com",
        )
    """

    def __init__(self) -> None:
        self._backend = None
        self._from_address: str = os.getenv("ZORK_EMAIL_FROM", "noreply@localhost")
        self._app_name: str = os.getenv("ZORK_APP_NAME", "Your App")
        self._base_url: str = os.getenv("ZORK_BASE_URL", "http://localhost:8000")
        # Template override callables — each receives a context dict and returns
        # (subject, html_body, text_body). None = use built-in default.
        self._template_password_reset = None
        self._template_verification = None
        self._template_welcome = None

    def use(self, backend) -> "_EmailConfig":
        """Plug in an :class:`~zork.email.EmailBackend` implementation."""
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
        from zork.email.templates import password_reset_email

        return password_reset_email(reset_url, self._app_name, expiry_minutes)

    def _render_verification(self, verify_url: str):
        ctx = {"verify_url": verify_url, "app_name": self._app_name}
        if self._template_verification:
            return self._template_verification(ctx)
        from zork.email.templates import email_verification_email

        return email_verification_email(verify_url, self._app_name)

    def _render_welcome(self, user_email: str):
        ctx = {"user_email": user_email, "app_name": self._app_name}
        if self._template_welcome:
            return self._template_welcome(ctx)
        from zork.email.templates import welcome_email

        return welcome_email(user_email, self._app_name)

    def _resolve_backend(self):
        if self._backend:
            return self._backend
        from zork.email.backends import ConsoleEmailBackend

        return ConsoleEmailBackend()

    async def send(self, message) -> None:
        """Dispatch ``message`` in the background (non-blocking).

        The sender address is filled in from ``configure(from_address=...)``
        if the message doesn't have one set. Failures are logged and swallowed
        so email errors never break the HTTP response.

        Can also be called directly from hooks for custom transactional emails::

            from zork.email import EmailMessage

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


class _StaticFilesConfig:
    """Fluent static files configuration facade — accessible via ``app.static()``.

    Example::

        app = Zork(database="app.db")
        app.static("/static", "./static")
        app.static("/assets", "./assets", html=True)
    """

    def __init__(self) -> None:
        self._configs: list[StaticFilesConfig] = []

    def mount(
        self,
        path: str,
        directory: str,
        *,
        name: str | None = None,
        html: bool = False,
        cache_ttl: int | None = None,
    ) -> "_StaticFilesConfig":
        """Mount a static files directory at a URL path.

        Args:
            path: URL path prefix (e.g., "/static")
            directory: Filesystem path (e.g., "./static")
            name: Mount name for internal reference (default: derived from path)
            html: Enable SPA fallback (serve index.html for 404s)
            cache_ttl: Cache TTL in seconds (None = use framework default)

        Returns:
            Self for chaining.

        Example::

            app.static("/static", "./static")
            app.static("/assets", "./assets")
            app.static("/", "./dist", html=True)  # SPA fallback
        """
        self._configs.append(
            StaticFilesConfig(
                path=path,
                directory=directory,
                name=name,
                html=html,
                cache_ttl=cache_ttl,
            )
        )
        return self

    def _is_configured(self) -> bool:
        """Check if any static files mounts are configured."""
        return bool(self._configs)

    def _get_configs(self) -> list[StaticFilesConfig]:
        """Get all static files configurations."""
        return list(self._configs)


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

    def route(
        self,
        path: str,
        methods: list[str] | None = None,
    ):
        """Decorator for adding custom routes to the app.

        This method creates a Starlette route that can be used with the
        @app.response() decorator for response transformation.

        Args:
            path: URL path, can include path parameters like "/posts/{id}"
            methods: HTTP methods to handle. Defaults to ["GET"].

        Returns:
            A decorator that registers the route.

        Example::

            from zork import Zork
            from pydantic import BaseModel

            app = Zork()

            class PostResponse(BaseModel):
                id: str
                title: str

            @app.response(PostResponse)
            @app.route("/posts/{id}")
            async def get_post(request):
                post = await db.fetch("SELECT * FROM posts WHERE id = ?",
                                      [request.path_params["id"]])
                return post[0] if post else None
        """
        if methods is None:
            methods = ["GET"]

        def decorator(func):
            route = Route(path, func, methods=methods)
            self._custom_routes = getattr(self, '_custom_routes', [])
            self._custom_routes.append(route)
            return func

        return decorator

    async def fire(self, event: str, payload, ctx):
        return await self._runner.fire(event, payload, ctx)


def _detect_auto_sync(database: str) -> bool:
    """Detect whether auto-sync should be enabled based on database URL.

    Auto-sync is enabled by default for SQLite (development-friendly).
    Auto-sync is disabled by default for PostgreSQL and MySQL (production).
    """
    db_lower = database.lower()
    # SQLite patterns
    if db_lower in ("app.db", ":memory:"):
        return True
    if db_lower.startswith("sqlite:///"):
        return True
    # PostgreSQL
    if "postgresql" in db_lower or db_lower.startswith("postgres://"):
        return False
    # MySQL
    if "mysql" in db_lower:
        return False
    # Default to False for unknown databases (safer)
    return False


class Zork:
    def __init__(
        self,
        database: str = "app.db",
        *,
        title: str = "Zork API",
        api_version: str = "1.0.0",
        auto_sync: bool | None = None,
        cors_allow_origins: list[str] | None = None,
        cors_allow_credentials: bool = False,
        cors_allow_methods: list[str] | None = None,
        cors_allow_headers: list[str] | None = None,
        version: str | None = None,
        version_prefix: str | None = None,
    ):
        self.database = database
        self.title = title
        self.api_version = api_version  # OpenAPI version

        # API versioning - none by default for backward compatibility
        self._version = version  # e.g., "v1", "v2"
        self._version_prefix = version_prefix  # e.g., "/api", "api"

        # Auto-sync detection: explicit > env var > detection
        if auto_sync is not None:
            self._auto_sync = auto_sync
        elif env_val := os.getenv("ZORK_AUTO_SYNC"):
            self._auto_sync = env_val.lower() in ("true", "1", "yes")
        else:
            self._auto_sync = _detect_auto_sync(database)

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
        # Phase 9: static files
        self.staticfiles: _StaticFilesConfig = _StaticFilesConfig()
        # Multi-DB: optional pre-configured backend (set via configure_database())
        self._db_backend_override = None
        # CORS - configure via constructor or fluent API
        self.cors: _CORSConfig = _CORSConfig()
        if cors_allow_origins is not None:
            self.cors.allow_origins(cors_allow_origins)
        if cors_allow_credentials:
            self.cors.allow_credentials(True)
        if cors_allow_methods is not None:
            self.cors.allow_methods(cors_allow_methods)
        if cors_allow_headers is not None:
            self.cors.allow_headers(cors_allow_headers)
        # Response model configs for custom routes
        self._response_configs: dict[str, dict] = {}

    @property
    def auto_sync(self) -> bool:
        """Whether auto-sync is enabled for this app.

        Auto-sync automatically adds missing columns on startup.
        Default is True for SQLite, False for PostgreSQL/MySQL.
        Can be overridden via constructor or ZORK_AUTO_SYNC env var.
        """
        return self._auto_sync

    @property
    def version_prefix(self) -> str | None:
        """Get the URL prefix for versioned routes.

        Returns None if versioning is not enabled.
        Returns e.g., "/api" or "/api/v1" depending on configuration.
        """
        if not self._version:
            return None
        prefix = self._version_prefix or "/api"
        v = self._version if self._version.startswith("v") else f"v{self._version}"
        return f"{prefix}/{v}"

    def configure_database(self, backend) -> "Zork":
        """Plug in a fully pre-configured :class:`~zork.db.backends.base.DatabaseBackend`.

        Takes precedence over ``ZORK_DATABASE_URL``, ``DATABASE_URL``, and
        the ``database=`` constructor argument.  Use this when you need full
        control over pool size, SSL, timeouts, or a custom driver::

            from zork.db.backends.postgresql import PostgreSQLBackend

            app.configure_database(
                PostgreSQLBackend(
                    url=os.environ["DATABASE_URL"],
                    min_size=2,
                    max_size=20,
                    ssl="require",
                )
            )

        You can also pass any class that implements the
        :class:`~zork.db.backends.base.DatabaseBackend` ABC (e.g. a Turso /
        libsql adapter).
        """
        self._db_backend_override = backend
        return self

    def configure_storage(self, backend) -> "Zork":
        """Set the file storage backend used by all ``FileField`` columns.

        Must be called before ``build()`` if any registered collection has a
        ``FileField``. Raises ``ZorkError`` at build time (not request time)
        if a ``FileField`` collection is registered without a storage backend.

        Example::

            from zork.storage import LocalFileBackend, S3CompatibleBackend

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

    def configure_redis(self, *, url: str) -> "Zork":
        """Configure Redis for all subsystems in one call.

        Enables Redis-backed cache, rate-limiting, and realtime broker unless
        the developer has already plugged in custom backends.

        Equivalent to setting ``ZORK_REDIS_URL`` environment variable but
        programmatic, which is useful in tests or when the URL is not known at
        module import time.
        """
        from zork.cache import redis_client as _rc

        _rc.configure(url=url)
        os.environ["ZORK_REDIS_URL"] = url
        return self

    def static(
        self,
        path: str,
        directory: str,
        *,
        name: str | None = None,
        html: bool = False,
        cache_ttl: int | None = None,
    ) -> "Zork":
        """Mount a static files directory at a URL path.

        Static files are served before API routes, so requests to matching
        paths are handled by the filesystem without hitting your Python code.

        Args:
            path: URL path prefix (e.g., "/static", "/assets")
            directory: Filesystem path (e.g., "./static", "./dist")
            name: Mount name for internal reference (default: derived from path)
            html: Enable SPA fallback (serve index.html for unmatched routes)
            cache_ttl: Cache TTL in seconds (None = use framework default)

        Returns:
            Self for chaining.

        Example::

            app = Zork(database="app.db")

            # Simple static mount
            app.static("/static", "./static")

            # Multiple mounts
            app.static("/assets", "./assets")
            app.static("/images", "./images")

            # SPA app with fallback (serves index.html for 404s)
            app.static("/", "./dist", html=True)
        """
        self.staticfiles.mount(
            path=path,
            directory=directory,
            name=name,
            html=html,
            cache_ttl=cache_ttl,
        )
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

        self._secret = os.getenv("ZORK_SECRET")
        if not self._secret:
            self._secret = secrets.token_urlsafe(32)
            logger.warning(
                "No ZORK_SECRET set — tokens will not survive restarts. "
                "Set ZORK_SECRET in your .env file."
            )
        return self._secret

    def _resolve_broker(self):
        """Select realtime broker based on ZORK_REALTIME_BROKER env var or Redis URL."""
        broker_type = os.getenv("ZORK_REALTIME_BROKER", "").lower()
        redis_url = os.getenv("ZORK_REDIS_URL")
        if broker_type == "redis" or (broker_type == "" and redis_url):
            try:
                from zork.realtime.redis_broker import RedisBroker

                logger.info("Using Redis realtime broker")
                return RedisBroker()
            except ImportError:
                logger.warning(
                    "RedisBroker requested but redis not installed — falling back to in-process broker"
                )
        return self._broker

    def build(self) -> Starlette:
        configure_from_env()

        if self._db_backend_override is not None:
            # Developer supplied a fully pre-configured backend — bypass URL resolution.
            db = Database.__new__(Database)
            db.url = self.database
            db._backend = self._db_backend_override
        else:
            db = Database(self.database)
        store = CollectionStore(db, auto_sync=self.auto_sync)
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

            # Warn if auto-sync is enabled with production databases
            if self.auto_sync and not _detect_auto_sync(self.database):
                logger.warning(
                    "⚠️  WARNING: Auto-sync is enabled in production. "
                    "This is intended for development only. "
                    "For production, set ZORK_AUTO_SYNC=false or use migrations. "
                    "Run `zork schema diff` to preview changes."
                )

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
                await cleanup_expired_refresh_tokens(db)
                logger.info("Auth tables ready")

            _init_done[0] = True

        app_runner = self._runner

        @asynccontextmanager
        async def lifespan(app: Starlette):
            await _init()
            await app_runner.fire("app:startup", None, ZorkContext.system())
            yield
            await app_runner.fire("app:shutdown", None, ZorkContext.system())
            await broker.close()
            await db.disconnect()
            logger.info("Database disconnected")
            # Close shared Redis client if one was created
            from zork.cache import redis_client as _rc

            await _rc.close()

        # Validate: if any collection has a FileField, a storage backend must be set
        from zork.collections.schema import FileField as _FileField
        from zork.errors import ZorkError as _ZorkError

        for name, (col, _) in collections.items():
            if any(isinstance(f, _FileField) for f in col.fields):
                if self._storage_backend is None:
                    raise _ZorkError(
                        500,
                        f"Collection '{name}' has a FileField but no storage backend is configured. "
                        "Call app.configure_storage(...) before app.build().",
                    )

        # Install orphan file cleanup hooks
        if self._storage_backend is not None:
            from zork.storage.cleanup import install_file_cleanup

            install_file_cleanup(self._registry, self._storage_backend, collections)

        routes: list[Route] = []

        async def health(request: Request) -> JSONResponse:
            return JSONResponse({"status": "ok"})

        async def index(request: Request) -> HTMLResponse:
            html_content = (
                Path(__file__).parent.joinpath("landingpage.html").read_text()
            )
            return HTMLResponse(html_content)

        routes.append(Route("/", index, methods=["GET"]))

        # Build version prefix for routes
        vprefix = self.version_prefix
        health_path = f"{vprefix}/health" if vprefix else "/api/health"
        routes.append(Route(health_path, health, methods=["GET"]))

        # Add static files mounts BEFORE collection routes
        # so they take precedence for matching paths (e.g., /static/*)
        if self.staticfiles._is_configured():
            static_routes = mount_static_files(self.staticfiles._get_configs())
            routes.extend(static_routes)
            logger.info(
                "Static files enabled (%d mount(s))",
                len(static_routes),
            )

        routes.extend(
            build_collection_routes(
                collections,
                store,
                storage_backend=self._storage_backend,
                prefix=vprefix or "/api",
            )
        )

        if auth:
            routes.extend(
                build_auth_routes(
                    auth, db, secret, email_config=self.email, prefix=vprefix
                )
            )

        # Install the auto-emit bridge and add realtime routes
        self.realtime._install_bridge(self._registry, collections)
        routes.extend(self.realtime._build_routes(db, secret, prefix=vprefix))

        # Add OpenAPI/Swagger routes
        from zork.openapi import ZorkOpenAPI

        openapi = ZorkOpenAPI(
            title=self.title,
            version=self.api_version,
            prefix=vprefix,
            collections=collections,
            auth_enabled=auth is not None,
        )
        routes.extend(openapi.build_routes())

        # Add custom routes registered via @app.route()
        custom_routes = getattr(self, "_custom_routes", [])
        if custom_routes:
            routes.extend(custom_routes)
            logger.info("Added %d custom route(s)", len(custom_routes))

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
            cors_config=self.cors._build_config()
            if self.cors._is_configured()
            else None,
        )

        if self.cors._is_configured():
            orig = self.cors._allow_origins
            creds = self.cors._allow_credentials
            if "*" in orig and creds:
                logger.warning(
                    "⚠️  WARNING: CORS is configured with allow_origins=['*'] and allow_credentials=True. "
                    "This is insecure. Use specific origins in production."
                )
            elif orig:
                logger.info("CORS enabled (origins: %s)", ", ".join(orig))

        # Wrap *outside* the existing middleware stack so lazy init fires first.
        return LazyInitMiddleware(wrapped)  # type: ignore[return-value]

    def serve(
        self, host: str = "0.0.0.0", port: int = 8000, reload: bool = False
    ) -> None:
        import uvicorn

        app = self.build()
        uvicorn.run(app, host=host, port=port)

    def route(
        self,
        path: str,
        methods: list[str] | None = None,
    ):
        """Decorator for adding custom routes to the app.

        This method creates a Starlette route that can be used with the
        @app.response() decorator for response transformation.

        Args:
            path: URL path, can include path parameters like "/posts/{id}"
            methods: HTTP methods to handle. Defaults to ["GET"].

        Returns:
            A decorator that registers the route.

        Example::

            from zork import Zork
            from pydantic import BaseModel

            app = Zork()

            class PostResponse(BaseModel):
                id: str
                title: str

            @app.response(PostResponse)
            @app.route("/posts/{id}")
            async def get_post(request):
                post = await db.fetch("SELECT * FROM posts WHERE id = ?",
                                      [request.path_params["id"]])
                return post[0] if post else None
        """
        if methods is None:
            methods = ["GET"]

        def decorator(func):
            route = Route(path, func, methods=methods)
            self._custom_routes = getattr(self, '_custom_routes', [])
            self._custom_routes.append(route)
            return func

        return decorator

    def response(
        self,
        model: type[BaseModel] | None = None,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
        exclude_none: bool = False,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        by_alias: bool = False,
    ):
        """Decorator for transforming custom route responses.

        This decorator wraps a route handler to transform its return value
        through a response model, controlling which fields are included/excluded
        and how serialization works.

        Args:
            model: Pydantic BaseModel class for response transformation.
                Fields in the model will be used to validate and serialize
                the response. Computed fields can be added via model_validator.
            include: Set of field names to include in the response.
            exclude: Set of field names to exclude from the response.
                Useful for hiding sensitive data.
            exclude_none: If True, fields with None values are excluded.
            exclude_unset: If True, fields not explicitly set are excluded.
            exclude_defaults: If True, fields with default values are excluded.
            by_alias: If True, use field aliases in output.

        Returns:
            A decorator that wraps the route handler.

        Example::

            from pydantic import BaseModel
            from zork import Zork

            app = Zork()

            class PostDetail(BaseModel):
                id: str
                title: str
                slug: str  # computed
                view_count: int

                @model_validator(mode="before")
                def compute_slug(cls, data):
                    if isinstance(data, dict) and "title" in data:
                        data["slug"] = data["title"].lower().replace(" ", "-")
                    return data

            @app.response(PostDetail, include={"id", "title", "slug"})
            @app.route("/posts/{id}")
            async def get_post(request):
                return await fetch_post(request.path_params["id"])

        Query parameter override::

            # Client can override via URL params:
            # GET /posts/1?fields=id,title&exclude=view_count
            # The query params take precedence over decorator config
        """
        from zork.response import ResponseModel

        def decorator(func):
            async def wrapper(request, *args, **kwargs):
                result = await func(request, *args, **kwargs)

                if result is None:
                    return result

                query_params = dict(request.query_params)
                effective_include = include
                effective_exclude = set(exclude) if exclude else set()
                effective_exclude_none = exclude_none
                effective_by_alias = by_alias

                if "fields" in query_params:
                    effective_include = set(query_params["fields"].split(","))
                if "exclude" in query_params:
                    effective_exclude.update(query_params["exclude"].split(","))
                if query_params.get("exclude_none") == "true":
                    effective_exclude_none = True

                response_model = ResponseModel(
                    model=model,
                    include=effective_include,
                    exclude=effective_exclude,
                    exclude_none=effective_exclude_none,
                    exclude_unset=exclude_unset,
                    exclude_defaults=exclude_defaults,
                    by_alias=effective_by_alias,
                )

                return response_model.transform(result)

            return wrapper

        return decorator
