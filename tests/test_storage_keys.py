"""Tests for key generation and filename sanitization."""
from __future__ import annotations

import re

import pytest

from zeno.storage.keys import generate_key, sanitize_filename


class TestSanitizeFilename:
    def test_normal_filename(self):
        assert sanitize_filename("photo.jpg") == "photo.jpg"

    def test_strips_path_traversal(self):
        result = sanitize_filename("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_replaces_spaces(self):
        result = sanitize_filename("my file name.pdf")
        assert " " not in result

    def test_preserves_alphanumeric_dashes(self):
        result = sanitize_filename("my-file_name.jpg")
        assert result == "my-file_name.jpg"

    def test_truncates_long_stem(self):
        long_name = "a" * 200 + ".jpg"
        result = sanitize_filename(long_name)
        stem, _, ext = result.rpartition(".")
        assert len(stem) <= 64

    def test_no_extension(self):
        result = sanitize_filename("noextension")
        assert result == "noextension"

    def test_special_chars_replaced(self):
        result = sanitize_filename("file<>:\"?*.jpg")
        assert "<" not in result
        assert ">" not in result
        assert "?" not in result
        assert "*" not in result


class TestGenerateKey:
    def test_format(self):
        key = generate_key("posts", "rec123", "cover", "photo.jpg")
        parts = key.split("/")
        assert parts[0] == "posts"
        assert parts[1] == "rec123"
        assert parts[2] == "cover"
        # Last part: {uuid_hex}_{filename}
        last = parts[3]
        uuid_part, _, name_part = last.partition("_")
        assert len(uuid_part) == 32  # hex uuid4
        assert name_part == "photo.jpg"

    def test_uniqueness(self):
        key1 = generate_key("posts", "1", "cover", "photo.jpg")
        key2 = generate_key("posts", "1", "cover", "photo.jpg")
        assert key1 != key2

    def test_sanitizes_filename_in_key(self):
        key = generate_key("posts", "1", "cover", "../../etc/passwd")
        assert ".." not in key
        assert key.startswith("posts/1/cover/")
