import logging
import uuid

from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from cinder.errors import CinderError

logger = logging.getLogger("cinder.pipeline")


async def _handle_cinder_error(request: Request, exc: CinderError) -> JSONResponse:
    return JSONResponse(
        {"status": exc.status_code, "error": exc.message},
        status_code=exc.status_code,
    )


async def _handle_unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        {"status": 500, "error": "Internal server error"},
        status_code=500,
    )


class ErrorHandlerMiddleware:
    """Thin middleware wrapper — exception handling is registered directly on
    the Starlette app via build_middleware_stack so it fires inside
    Starlette's own ServerErrorMiddleware/ExceptionMiddleware layer."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


class RequestIDMiddleware:
    """Generates a UUID4 request ID and adds it to the response headers."""

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


def build_middleware_stack(
    app: ASGIApp,
    *,
    db=None,
    secret: str | None = None,
) -> ASGIApp:
    """Wrap the app with the standard Cinder middleware stack.

    Order (outermost to innermost):
    1. ErrorHandler — catches all errors
    2. RequestID — adds X-Request-ID header
    3. CORS — handles cross-origin requests
    """
    # Register exception handlers on the inner Starlette app before wrapping.
    # Starlette's internal ServerErrorMiddleware handles exceptions before our
    # outer middleware can see them, so we must hook in at the Starlette level.
    from starlette.applications import Starlette

    if isinstance(app, Starlette):
        app.add_exception_handler(CinderError, _handle_cinder_error)
        app.add_exception_handler(Exception, _handle_unhandled_error)

    # CORS (innermost)
    app = CORSMiddleware(
        app,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app = RequestIDMiddleware(app)
    app = ErrorHandlerMiddleware(app)
    return app
