from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path


class FileStorageBackend(ABC):
    """Abstract base class for Zork file storage backends.

    Subclass this to implement a custom storage provider. The only required
    methods are ``put``, ``get``, and ``delete``. Override ``signed_url`` and/or
    ``url`` if your backend supports presigned or public URLs.
    """

    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """Store ``data`` at ``key`` with the given MIME ``content_type``."""

    @abstractmethod
    async def get(self, key: str) -> tuple[bytes, str]:
        """Return ``(data, content_type)`` for the file at ``key``.

        Raises ``FileNotFoundError`` if the key does not exist.
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete the file at ``key``.

        Should be a no-op (not raise) if the key does not exist.
        """

    async def signed_url(self, key: str, expires_in: int = 900) -> str | None:
        """Return a time-limited URL for authenticated download, or ``None``.

        When ``None`` is returned, Zork proxies the file bytes through the
        server instead of redirecting. Defaults to ``None`` (proxy mode).

        ``expires_in`` is the lifetime of the URL in seconds (default 15 min).
        """
        return None

    async def url(self, key: str) -> str | None:
        """Return a permanent public URL for the file, or ``None``.

        Used for ``FileField(public=True)`` fields. When ``None`` is returned,
        Zork proxies the bytes. Defaults to ``None``.
        """
        return None


class LocalFileBackend(FileStorageBackend):
    """Store files on the local filesystem under ``base_path``.

    Zero external dependencies. Files are always served by proxying bytes
    through the Zork server (no signed URLs, no CDN).

    Example::

        app.configure_storage(LocalFileBackend("./uploads"))
    """

    def __init__(self, base_path: str = "./uploads") -> None:
        self._base = Path(base_path).resolve()

    def _full_path(self, key: str) -> Path:
        # Resolve and verify the path stays inside base_path (belt-and-suspenders
        # against any path traversal that slips past key generation).
        resolved = (self._base / key).resolve()
        if not str(resolved).startswith(str(self._base)):
            raise ValueError(f"Key '{key}' resolves outside the storage base path.")
        return resolved

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._full_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> tuple[bytes, str]:
        path = self._full_path(key)
        if not path.exists():
            raise FileNotFoundError(f"No file at key '{key}'")
        # Best-effort MIME detection from extension; caller already knows the
        # stored content_type but we don't persist it separately for local files.
        import mimetypes

        content_type, _ = mimetypes.guess_type(str(path))
        return path.read_bytes(), content_type or "application/octet-stream"

    async def delete(self, key: str) -> None:
        path = self._full_path(key)
        try:
            path.unlink()
            # Remove empty parent directories up to (but not including) base_path
            parent = path.parent
            while parent != self._base:
                try:
                    parent.rmdir()  # only removes if empty
                    parent = parent.parent
                except OSError:
                    break
        except FileNotFoundError:
            pass  # already gone — treat as success
