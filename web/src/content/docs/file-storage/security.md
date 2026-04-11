---
title: Security
description: Access control for file upload and download routes
sidebar:
  order: 3
---

## Download access

By default, file download routes respect the collection's access control rules:

- If the collection uses `read:owner`, only the record's owner can download files from it
- If the collection uses `read:authenticated`, any authenticated user can download
- If the collection uses `read:public`, anyone can download

### Public files

Set `public=True` on a `FileField` to skip authentication entirely for that field's download route:

```python
FileField("avatar", public=True)
FileField("cover_image", public=True)
```

Use this for assets you intentionally want publicly accessible (profile pictures, cover images, product photos).

### Private files

Without `public=True`, the download route requires a valid JWT token. Ownership rules are enforced the same way as for regular collection reads.

## Upload access

Upload routes follow the collection's `write` rules:

- `write:authenticated` — any authenticated user can upload
- `write:owner` — only the record owner can upload to their own record
- `write:admin` — only admins can upload

## File type validation

Cinder validates MIME types on upload using the `allowed_types` option:

```python
FileField("doc", allowed_types=["application/pdf", "application/msword"])
FileField("image", allowed_types=["image/*"])
FileField("any", allowed_types=["*/*"])   # no restriction (default)
```

Pattern matching:
- `"image/*"` matches `image/jpeg`, `image/png`, `image/webp`, etc.
- `"application/pdf"` matches only that exact MIME type
- `"*/*"` matches everything

## File size limits

Set `max_size` in bytes:

```python
FileField("avatar", max_size=2_000_000)   # 2 MB
FileField("video", max_size=100_000_000)  # 100 MB
```

Files exceeding the limit are rejected with `413 Payload Too Large`.

## Keys and filenames

Cinder generates a unique, sanitised storage key for each uploaded file:

```
{collection}/{record_id}/{field_name}/{uuid}.{ext}
```

For example: `posts/abc123/cover/f1e2d3c4.jpg`

The original filename is stored in the metadata but is not used as the storage key. This prevents path traversal and filename collision issues.

## Orphan cleanup

When a record containing file fields is deleted, Cinder automatically deletes the associated files from the storage backend through `after_delete` hooks. No manual cleanup is required.
