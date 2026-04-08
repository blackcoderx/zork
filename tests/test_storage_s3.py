"""Tests for S3CompatibleBackend provider presets (no real network calls)."""
from __future__ import annotations

import pytest

from cinder.storage.s3 import S3CompatibleBackend


class TestS3CompatibleBackendPresets:
    def test_aws_preset(self):
        b = S3CompatibleBackend.aws("bucket", "key", "secret", region="eu-west-1")
        assert b._bucket == "bucket"
        assert b._region_name == "eu-west-1"
        assert b._endpoint_url is None

    def test_r2_preset(self):
        b = S3CompatibleBackend.r2("acct123", "bucket", "key", "secret")
        assert "acct123.r2.cloudflarestorage.com" in b._endpoint_url
        assert b._region_name == "auto"

    def test_minio_preset(self):
        b = S3CompatibleBackend.minio("http://localhost:9000", "bucket", "key", "secret")
        assert b._endpoint_url == "http://localhost:9000"
        assert b._region_name == "us-east-1"
        assert b._extra_config.get("signature_version") == "s3v4"

    def test_backblaze_preset(self):
        b = S3CompatibleBackend.backblaze(
            "https://s3.us-west-001.backblazeb2.com", "bucket", "kid", "appkey"
        )
        assert "backblazeb2.com" in b._endpoint_url
        assert b._region_name == "us-west-001"

    def test_digitalocean_preset(self):
        b = S3CompatibleBackend.digitalocean("nyc3", "my-space", "key", "secret")
        assert "nyc3.digitaloceanspaces.com" in b._endpoint_url
        assert b._region_name == "nyc3"
        assert b._bucket == "my-space"

    def test_wasabi_preset(self):
        b = S3CompatibleBackend.wasabi("us-east-1", "bucket", "key", "secret")
        assert "wasabisys.com" in b._endpoint_url
        assert b._region_name == "us-east-1"

    def test_gcs_preset(self):
        b = S3CompatibleBackend.gcs("bucket", "hmac-key", "hmac-secret")
        assert b._endpoint_url == "https://storage.googleapis.com"
        assert b._region_name == "auto"

    def test_key_prefix(self):
        b = S3CompatibleBackend.aws("bucket", "key", "secret", region="us-east-1")
        b._key_prefix = "myapp"
        assert b._prefixed("posts/1/cover/file.jpg") == "myapp/posts/1/cover/file.jpg"

    def test_no_prefix(self):
        b = S3CompatibleBackend.aws("bucket", "key", "secret")
        assert b._prefixed("posts/1/cover/file.jpg") == "posts/1/cover/file.jpg"

    def test_missing_boto3_raises_import_error(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "boto3":
                raise ImportError("no boto3")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        b = S3CompatibleBackend.aws("bucket", "key", "secret")
        b._client = None  # force re-init
        with pytest.raises(ImportError, match="boto3 is required"):
            b._get_client()
