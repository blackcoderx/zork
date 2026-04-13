"""Tests for LocalFileBackend and the FileStorageBackend ABC."""
from __future__ import annotations

import pytest

from zeno.storage.backends import LocalFileBackend


class TestLocalFileBackend:
    @pytest.fixture
    def backend(self, tmp_path):
        return LocalFileBackend(str(tmp_path / "uploads"))

    async def test_put_and_get_roundtrip(self, backend):
        data = b"hello file"
        await backend.put("posts/1/cover/abc_photo.jpg", data, "image/jpeg")
        result, mime = await backend.get("posts/1/cover/abc_photo.jpg")
        assert result == data

    async def test_delete_removes_file(self, backend, tmp_path):
        key = "posts/1/cover/abc_photo.jpg"
        await backend.put(key, b"data", "image/jpeg")
        await backend.delete(key)
        with pytest.raises(FileNotFoundError):
            await backend.get(key)

    async def test_delete_nonexistent_is_noop(self, backend):
        await backend.delete("nonexistent/key.jpg")  # must not raise

    async def test_signed_url_returns_none(self, backend):
        assert await backend.signed_url("any/key") is None

    async def test_url_returns_none(self, backend):
        assert await backend.url("any/key") is None

    async def test_get_nonexistent_raises(self, backend):
        with pytest.raises(FileNotFoundError):
            await backend.get("does/not/exist.jpg")

    async def test_path_traversal_rejected(self, backend):
        with pytest.raises(ValueError):
            await backend.put("../../etc/passwd", b"pwned", "text/plain")

    async def test_delete_cleans_empty_directories(self, backend, tmp_path):
        key = "posts/1/cover/abc.jpg"
        await backend.put(key, b"x", "image/jpeg")
        await backend.delete(key)
        # Parent directories should be removed since they're empty
        parent = tmp_path / "uploads" / "posts" / "1" / "cover"
        assert not parent.exists()
