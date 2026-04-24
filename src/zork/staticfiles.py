"""Static file serving subsystem for Zork.

Uses Starlette's StaticFiles for production-grade static file serving with:
- Path traversal protection
- Automatic MIME types
- HEAD/GET handling
- Cache headers (ETag, Last-Modified)
- SPA fallback support
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.routing import Route


class StaticFilesConfig:
    """Configuration for a single static files mount point.

    Attributes:
        path: URL path prefix (e.g., "/static")
        directory: Filesystem path (e.g., "./static")
        name: Mount name for internal reference
        html: Enable SPA fallback (serve index.html for 404s)
        cache_ttl: Cache TTL in seconds (None = no cache)
    """

    def __init__(
        self,
        path: str,
        directory: str,
        *,
        name: str | None = None,
        html: bool = False,
        cache_ttl: int | None = None,
    ) -> None:
        self.path = path
        self.directory = directory
        self.name = name or path.strip("/").replace("/", "_") or "static"
        self.html = html
        self.cache_ttl = cache_ttl

    def validate(self) -> None:
        """Validate the static files configuration.

        Raises:
            ValueError: If the directory does not exist.
        """
        dir_path = Path(self.directory).resolve()
        if not dir_path.is_dir():
            raise ValueError(
                f"Static files directory does not exist: {self.directory!r} "
                f"(resolved to {dir_path})"
            )

    def get_cache_headers(self) -> dict[str, str] | None:
        """Get cache control headers if cache_ttl is configured."""
        if self.cache_ttl is None:
            return None
        return {
            "Cache-Control": f"public, max-age={self.cache_ttl}",
        }


def mount_static_files(configs: list[StaticFilesConfig]) -> list[Route]:
    """Build Starlette routes for static file mounts.

    This function creates mount routes that handle static file serving with:
    - Path traversal protection
    - Automatic MIME type detection
    - Optional SPA fallback (html=True)
    - Configurable caching

    Args:
        configs: List of StaticFilesConfig objects.

    Returns:
        List of Starlette Route objects.

    Example::

        configs = [
            StaticFilesConfig("/static", "./static"),
            StaticFilesConfig("/assets", "./assets", html=False),
        ]
        routes = mount_static_files(configs)
    """
    from starlette.staticfiles import StaticFiles

    routes: list[Route] = []
    for config in configs:
        config.validate()

        static_files = StaticFiles(
            directory=config.directory,
            html=config.html,
            check_dir=True,
        )

        from starlette.routing import Mount

        route = Mount(
            path=config.path,
            name=config.name,
            app=static_files,
        )
        routes.append(route)

    return routes
