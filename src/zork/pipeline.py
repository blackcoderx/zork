import logging
import uuid

from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from zork.auth.models import is_blocked
from zork.auth.tokens import decode_token
from zork.errors import ZorkError
from zork.hooks.context import ZorkContext
from zork.hooks.runner import HookRunner

logger = logging.getLogger("zork.pipeline")


async def _handle_zork_error(request: Request, exc: ZorkError) -> JSONResponse:
    return JSONResponse(
        {"status": exc.status_code, "error": exc.message},
        status_code=exc.status_code,
    )


def _make_unhandled_error_handler(runner: HookRunner | None):
    async def _handle_unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        if runner is not None:
            try:
                ctx = ZorkContext.from_request(request, operation="error")
                await runner.fire("app:error", exc, ctx)
            except Exception:
                logger.exception("app:error hook raised")
        return JSONResponse(
            {"status": 500, "error": "Internal server error"},
            status_code=500,
        )

    return _handle_unhandled_error


class ErrorHandlerMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_request_id)


class AuthMiddleware:
    def __init__(self, app: ASGIApp, *, db, secret: str):
        self.app = app
        self.db = db
        self.secret = secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            scope.setdefault("state", {})
            scope["state"]["user"] = None

            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()

            if auth_header.startswith("Bearer "):
                token = auth_header[len("Bearer ") :]
                try:
                    payload = decode_token(token, self.secret)
                except Exception:
                    payload = None

                if payload is not None:
                    jti = payload.get("jti")
                    blocked = jti and await is_blocked(self.db, jti)
                    if not blocked:
                        user_id = payload.get("sub")
                        if user_id:
                            row = await self.db.fetch_one(
                                "SELECT * FROM _users WHERE id = ?", (user_id,)
                            )
                            if row:
                                user = dict(row)
                                user.pop("password", None)
                                scope["state"]["user"] = user

        await self.app(scope, receive, send)


def build_middleware_stack(
    app: ASGIApp,
    *,
    db=None,
    secret: str | None = None,
    hook_runner: HookRunner | None = None,
    cache_middleware=None,
    ratelimit_middleware=None,
    cors_config: dict | None = None,
) -> ASGIApp:
    """Wrap the app with the standard Zork middleware stack.

    Order (outermost to innermost):
    1. ErrorHandler — catches all errors
    2. RequestID — adds X-Request-ID header
    3. CORS — handles cross-origin requests (optional)
    4. RateLimit — enforces per-IP/user request limits (optional)
    5. Cache — cache-aside for GET responses (optional)
    6. Auth — resolves JWT and sets request.state.user (when db+secret provided)
    """
    from starlette.applications import Starlette

    if isinstance(app, Starlette):
        app.add_exception_handler(ZorkError, _handle_zork_error)
        app.add_exception_handler(Exception, _make_unhandled_error_handler(hook_runner))

    if db is not None and secret is not None:
        app = AuthMiddleware(app, db=db, secret=secret)

    if cache_middleware is not None:
        app = cache_middleware(app)

    if ratelimit_middleware is not None:
        app = ratelimit_middleware(app)

    if cors_config is not None:
        app = CORSMiddleware(
            app,
            allow_origins=cors_config.get("allow_origins", ["*"]),
            allow_credentials=cors_config.get("allow_credentials", False),
            allow_methods=cors_config.get("allow_methods", ["*"]),
            allow_headers=cors_config.get("allow_headers", ["*"]),
            expose_headers=cors_config.get("expose_headers", []),
            max_age=cors_config.get("max_age"),
        )
    else:
        from starlette.middleware.base import BaseHTTPMiddleware

        class DisabledCORSMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                response = await call_next(request)
                return response

        app = DisabledCORSMiddleware(app)

    app = RequestIDMiddleware(app)
    app = ErrorHandlerMiddleware(app)
    return app
