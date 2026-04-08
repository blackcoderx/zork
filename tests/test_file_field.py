"""Tests for FileField schema definition."""
from __future__ import annotations

import json

import pytest

from cinder.collections.schema import FileField


class TestFileField:
    def test_defaults(self):
        f = FileField("cover")
        assert f.max_size == 10_000_000
        assert f.allowed_types == ["*/*"]
        assert f.multiple is False
        assert f.public is False
        assert f.required is False

    def test_sqlite_type(self):
        assert FileField("cover").sqlite_type() == "TEXT"

    def test_serialize_single(self):
        f = FileField("cover")
        meta = {"key": "posts/1/cover/abc.jpg", "name": "abc.jpg", "size": 100, "mime": "image/jpeg"}
        serialized = f.serialize(meta)
        assert json.loads(serialized) == meta

    def test_serialize_none(self):
        f = FileField("cover")
        assert f.serialize(None) is None

    def test_deserialize_single(self):
        f = FileField("cover")
        meta = {"key": "k", "name": "n", "size": 1, "mime": "image/jpeg"}
        assert f.deserialize(json.dumps(meta)) == meta

    def test_deserialize_none(self):
        f = FileField("cover")
        assert f.deserialize(None) is None

    def test_deserialize_invalid_json(self):
        f = FileField("cover")
        assert f.deserialize("not-json{") is None

    def test_serialize_multiple(self):
        f = FileField("attachments", multiple=True)
        entries = [
            {"key": "k1", "name": "a.pdf", "size": 100, "mime": "application/pdf"},
            {"key": "k2", "name": "b.pdf", "size": 200, "mime": "application/pdf"},
        ]
        result = f.deserialize(f.serialize(entries))
        assert result == entries

    def test_matches_mime_wildcard(self):
        f = FileField("cover", allowed_types=["*/*"])
        assert f.matches_mime("image/jpeg")
        assert f.matches_mime("application/pdf")
        assert f.matches_mime("video/mp4")

    def test_matches_mime_type_wildcard(self):
        f = FileField("cover", allowed_types=["image/*"])
        assert f.matches_mime("image/jpeg")
        assert f.matches_mime("image/png")
        assert not f.matches_mime("application/pdf")

    def test_matches_mime_exact(self):
        f = FileField("doc", allowed_types=["application/pdf"])
        assert f.matches_mime("application/pdf")
        assert not f.matches_mime("application/zip")

    def test_matches_mime_multiple_patterns(self):
        f = FileField("file", allowed_types=["image/*", "application/pdf"])
        assert f.matches_mime("image/jpeg")
        assert f.matches_mime("application/pdf")
        assert not f.matches_mime("video/mp4")

    def test_column_sql(self):
        sql = FileField("cover").column_sql()
        assert "cover" in sql
        assert "TEXT" in sql
