---
title: Setup
description: Add file upload support to your collections
sidebar:
  order: 1
---

File storage lets you attach uploaded files to any collection record. The API generates upload, download, and delete endpoints automatically for every `FileField`.

## 1. Add a FileField to your collection

```python
from cinder import Collection, TextField, FileField

posts = Collection("posts", fields=[
    TextField("title", required=True),
    FileField("cover", max_size=2_000_000, allowed_types=["image/*"], public=True),
    FileField("attachments", multiple=True, allowed_types=["application/pdf"]),
])
```

## 2. Configure a storage backend

```python
from cinder.storage import LocalFileBackend

app.configure_storage(LocalFileBackend("./uploads"))
app.register(posts)
```

A storage backend **must** be configured if any collection has a `FileField`. Cinder raises an error at startup if this is missing.

## 3. Generated routes

For each `FileField`, Cinder generates:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/{collection}/{id}/files/{field}` | Upload a file |
| `GET` | `/api/{collection}/{id}/files/{field}` | Download the file |
| `DELETE` | `/api/{collection}/{id}/files/{field}` | Delete the file |

For `multiple=True` fields, `POST` appends to the list. `GET` returns a list of metadata objects.

## Uploading a file

Use `multipart/form-data` with the field name `file`:

```bash
curl -X POST /api/posts/some-id/files/cover \
  -H "Authorization: Bearer eyJ..." \
  -F "file=@/path/to/image.jpg"
```

Returns `201` with the **full updated record** including the file metadata stored in the field:

```json
{
  "id": "some-id",
  "title": "My Post",
  "cover": {
    "key": "posts/some-id/cover/abc123.jpg",
    "name": "image.jpg",
    "mime": "image/jpeg",
    "size": 45230
  },
  "created_at": "...",
  "updated_at": "..."
}
```

For `multiple=True` fields, the `cover` field will be a list and each upload appends to it.

## Downloading a file

```bash
GET /api/posts/some-id/files/cover
```

For `public=True` fields, no authentication is required. The server redirects to a signed URL (S3) or proxies the bytes (local storage).

For `multiple=True` fields, you must specify which file to download using `?index=N`:

```bash
GET /api/posts/some-id/files/attachments?index=0   # first file
GET /api/posts/some-id/files/attachments?index=2   # third file
```

## Deleting a file

```bash
DELETE /api/posts/some-id/files/cover
```

Returns the full updated record with the field set to `null`.

For `multiple=True` fields, you must specify which file(s) to delete:

```bash
# Delete a specific file by index
DELETE /api/posts/some-id/files/attachments?index=1

# Delete all files
DELETE /api/posts/some-id/files/attachments?all=true
```

Omitting both `?index` and `?all` on a multi-file field returns `400 Bad Request`.

## FileField options

| Option | Default | Description |
|--------|---------|-------------|
| `max_size` | `10_000_000` | Max file size in bytes |
| `allowed_types` | `["*/*"]` | MIME type patterns (`"image/*"`, `"application/pdf"`) |
| `multiple` | `False` | Allow multiple files |
| `public` | `False` | Skip auth on the download route |

## Orphan cleanup

When a record is deleted, Cinder automatically deletes any files attached to it through lifecycle hooks — no manual cleanup needed.

## Next: choose a backend

- [Local disk](/file-storage/backends/) — zero config, dev-friendly
- [S3-compatible](/file-storage/backends/) — AWS, Cloudflare R2, MinIO, and more
