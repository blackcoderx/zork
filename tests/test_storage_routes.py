"""Integration tests for file upload / download / delete routes."""
from __future__ import annotations

import io
import json

import pytest
from starlette.testclient import TestClient

from zeno.app import Zeno
from zeno.auth import Auth
from zeno.collections.schema import Collection, TextField, FileField
from zeno.storage.backends import LocalFileBackend


@pytest.fixture
def app_with_files(db_path, tmp_path):
    """A Zeno app with a Posts collection that has a FileField."""
    app = Zeno(database=db_path)

    posts = Collection("posts", fields=[
        TextField("title", required=True),
        FileField("cover", max_size=1_000_000, allowed_types=["image/*"], public=True),
        FileField("attachments", multiple=True, allowed_types=["application/pdf"]),
    ])

    app.register(posts, auth=["read:public", "write:authenticated"])
    app.use_auth(Auth(allow_registration=True))
    app.configure_storage(LocalFileBackend(str(tmp_path / "uploads")))

    with TestClient(app.build()) as client:
        yield client


@pytest.fixture
def token_and_post(app_with_files):
    """Register a user, create a post, return (client, token, post_id)."""
    client = app_with_files
    reg = client.post("/api/auth/register", json={"email": "u@x.com", "password": "pass1234"})
    assert reg.status_code == 201
    token = reg.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    post = client.post("/api/posts", json={"title": "Hello"}, headers=headers)
    assert post.status_code == 201
    return client, headers, post.json()["id"]


class TestUpload:
    def test_upload_image_succeeds(self, token_and_post):
        client, headers, post_id = token_and_post
        img = b"\xff\xd8\xff" + b"\x00" * 100  # JPEG magic bytes
        resp = client.post(
            f"/api/posts/{post_id}/files/cover",
            files={"file": ("photo.jpg", io.BytesIO(img), "image/jpeg")},
            headers=headers,
        )
        assert resp.status_code == 201
        record = resp.json()
        cover = record["cover"]
        assert cover is not None
        assert cover["name"] == "photo.jpg"
        assert cover["mime"] == "image/jpeg"
        assert cover["size"] == len(img)
        assert "key" in cover

    def test_upload_requires_auth(self, token_and_post):
        client, _, post_id = token_and_post
        img = b"\xff\xd8\xff" + b"\x00" * 10
        resp = client.post(
            f"/api/posts/{post_id}/files/cover",
            files={"file": ("photo.jpg", io.BytesIO(img), "image/jpeg")},
        )
        assert resp.status_code == 401

    def test_upload_rejects_wrong_mime(self, token_and_post):
        client, headers, post_id = token_and_post
        resp = client.post(
            f"/api/posts/{post_id}/files/cover",
            files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4 content"), "application/pdf")},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_upload_rejects_oversized_file(self, token_and_post, tmp_path):
        client, headers, post_id = token_and_post
        big = b"\xff\xd8\xff" + b"\x00" * 2_000_000  # > 1MB limit
        resp = client.post(
            f"/api/posts/{post_id}/files/cover",
            files={"file": ("big.jpg", io.BytesIO(big), "image/jpeg")},
            headers=headers,
        )
        assert resp.status_code == 413

    def test_upload_rejects_non_multipart(self, token_and_post):
        client, headers, post_id = token_and_post
        resp = client.post(
            f"/api/posts/{post_id}/files/cover",
            content=b"raw bytes",
            headers={**headers, "content-type": "application/octet-stream"},
        )
        assert resp.status_code == 415

    def test_upload_404_for_missing_record(self, token_and_post):
        client, headers, _ = token_and_post
        img = b"\xff\xd8\xff" + b"\x00" * 10
        resp = client.post(
            "/api/posts/nonexistent/files/cover",
            files={"file": ("photo.jpg", io.BytesIO(img), "image/jpeg")},
            headers=headers,
        )
        assert resp.status_code == 404

    def test_upload_multiple_appends(self, token_and_post):
        client, headers, post_id = token_and_post
        pdf = b"%PDF-1.4" + b"\x00" * 50
        resp1 = client.post(
            f"/api/posts/{post_id}/files/attachments",
            files={"file": ("a.pdf", io.BytesIO(pdf), "application/pdf")},
            headers=headers,
        )
        assert resp1.status_code == 201
        resp2 = client.post(
            f"/api/posts/{post_id}/files/attachments",
            files={"file": ("b.pdf", io.BytesIO(pdf), "application/pdf")},
            headers=headers,
        )
        assert resp2.status_code == 201
        attachments = resp2.json()["attachments"]
        assert isinstance(attachments, list)
        assert len(attachments) == 2

    def test_upload_single_replaces_existing(self, token_and_post):
        client, headers, post_id = token_and_post
        img = b"\xff\xd8\xff" + b"\x00" * 10
        client.post(
            f"/api/posts/{post_id}/files/cover",
            files={"file": ("first.jpg", io.BytesIO(img), "image/jpeg")},
            headers=headers,
        )
        resp = client.post(
            f"/api/posts/{post_id}/files/cover",
            files={"file": ("second.jpg", io.BytesIO(img), "image/jpeg")},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["cover"]["name"] == "second.jpg"


class TestDownload:
    def _upload(self, client, headers, post_id, content=None, field="cover"):
        img = content or (b"\xff\xd8\xff" + b"\x00" * 10)
        resp = client.post(
            f"/api/posts/{post_id}/files/{field}",
            files={"file": ("photo.jpg", io.BytesIO(img), "image/jpeg")},
            headers=headers,
        )
        assert resp.status_code == 201
        return img

    def test_download_public_field_no_auth(self, token_and_post):
        client, headers, post_id = token_and_post
        img = self._upload(client, headers, post_id)
        # cover is public=True — no auth needed for GET
        resp = client.get(f"/api/posts/{post_id}/files/cover")
        assert resp.status_code == 200
        assert resp.content == img

    def test_download_private_field_requires_auth(self, token_and_post):
        client, headers, post_id = token_and_post
        pdf = b"%PDF-1.4" + b"\x00" * 50
        client.post(
            f"/api/posts/{post_id}/files/attachments",
            files={"file": ("a.pdf", io.BytesIO(pdf), "application/pdf")},
            headers=headers,
        )
        # attachments is not public — unauthenticated download should fail
        resp = client.get(f"/api/posts/{post_id}/files/attachments?index=0")
        assert resp.status_code == 401

    def test_download_private_field_with_auth(self, token_and_post):
        client, headers, post_id = token_and_post
        pdf = b"%PDF-1.4" + b"\x00" * 50
        client.post(
            f"/api/posts/{post_id}/files/attachments",
            files={"file": ("a.pdf", io.BytesIO(pdf), "application/pdf")},
            headers=headers,
        )
        resp = client.get(f"/api/posts/{post_id}/files/attachments?index=0", headers=headers)
        assert resp.status_code == 200
        assert resp.content == pdf

    def test_download_404_when_no_file(self, token_and_post):
        client, _, post_id = token_and_post
        resp = client.get(f"/api/posts/{post_id}/files/cover")
        assert resp.status_code == 404

    def test_download_multiple_requires_index(self, token_and_post):
        client, headers, post_id = token_and_post
        pdf = b"%PDF-1.4" + b"\x00" * 10
        client.post(
            f"/api/posts/{post_id}/files/attachments",
            files={"file": ("a.pdf", io.BytesIO(pdf), "application/pdf")},
            headers=headers,
        )
        resp = client.get(f"/api/posts/{post_id}/files/attachments", headers=headers)
        assert resp.status_code == 400


class TestDelete:
    def _upload(self, client, headers, post_id, field="cover"):
        img = b"\xff\xd8\xff" + b"\x00" * 10
        resp = client.post(
            f"/api/posts/{post_id}/files/{field}",
            files={"file": ("photo.jpg", io.BytesIO(img), "image/jpeg")},
            headers=headers,
        )
        assert resp.status_code == 201

    def test_delete_single_file(self, token_and_post):
        client, headers, post_id = token_and_post
        self._upload(client, headers, post_id)
        resp = client.delete(f"/api/posts/{post_id}/files/cover", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["cover"] is None

    def test_delete_requires_auth(self, token_and_post):
        client, headers, post_id = token_and_post
        self._upload(client, headers, post_id)
        resp = client.delete(f"/api/posts/{post_id}/files/cover")
        assert resp.status_code == 401

    def test_delete_multiple_by_index(self, token_and_post):
        client, headers, post_id = token_and_post
        pdf = b"%PDF-1.4" + b"\x00" * 10
        for name in ("a.pdf", "b.pdf"):
            client.post(
                f"/api/posts/{post_id}/files/attachments",
                files={"file": (name, io.BytesIO(pdf), "application/pdf")},
                headers=headers,
            )
        resp = client.delete(
            f"/api/posts/{post_id}/files/attachments?index=0", headers=headers
        )
        assert resp.status_code == 200
        remaining = resp.json()["attachments"]
        assert len(remaining) == 1
        assert remaining[0]["name"] == "b.pdf"

    def test_delete_all_multiple_files(self, token_and_post):
        client, headers, post_id = token_and_post
        pdf = b"%PDF-1.4" + b"\x00" * 10
        for _ in range(3):
            client.post(
                f"/api/posts/{post_id}/files/attachments",
                files={"file": ("doc.pdf", io.BytesIO(pdf), "application/pdf")},
                headers=headers,
            )
        resp = client.delete(
            f"/api/posts/{post_id}/files/attachments?all=true", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["attachments"] is None


class TestCleanup:
    def test_orphan_cleanup_on_record_delete(self, token_and_post, tmp_path):
        client, headers, post_id = token_and_post
        img = b"\xff\xd8\xff" + b"\x00" * 10
        upload_resp = client.post(
            f"/api/posts/{post_id}/files/cover",
            files={"file": ("photo.jpg", io.BytesIO(img), "image/jpeg")},
            headers=headers,
        )
        assert upload_resp.status_code == 201
        key = upload_resp.json()["cover"]["key"]
        file_path = tmp_path / "uploads" / key

        assert file_path.exists()

        del_resp = client.delete(f"/api/posts/{post_id}", headers=headers)
        assert del_resp.status_code == 200

        # File should be cleaned up by the after_delete hook
        assert not file_path.exists()


class TestBuildValidation:
    def test_build_fails_without_storage_backend(self, db_path):
        app = Zeno(database=db_path)
        posts = Collection("posts", fields=[
            TextField("title"),
            FileField("cover"),
        ])
        app.register(posts)
        with pytest.raises(Exception, match="storage backend"):
            app.build()
