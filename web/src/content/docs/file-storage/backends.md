---
title: Storage Backends
description: Local disk and S3-compatible storage backends
sidebar:
  order: 2
---

## LocalFileBackend

Stores files on the local filesystem. No extra dependencies required.

```python
from cinder.storage import LocalFileBackend

app.configure_storage(LocalFileBackend("./uploads"))
```

Files are served directly through Cinder's download route. Suitable for development and single-server deployments.

---

## S3CompatibleBackend

Stores files in any S3-compatible object store. Requires the `s3` extra:

```bash
pip install "cinder[s3]"
uv add "cinder[s3]"
```

### AWS S3

```python
from cinder.storage import S3CompatibleBackend

app.configure_storage(S3CompatibleBackend.aws(
    bucket="my-bucket",
    access_key="AKIA...",
    secret_key="...",
    region="us-east-1",
))
```

### Cloudflare R2

```python
app.configure_storage(S3CompatibleBackend.r2(
    account_id="your-account-id",
    bucket="my-bucket",
    access_key="...",
    secret_key="...",
))
```

### MinIO

```python
app.configure_storage(S3CompatibleBackend.minio(
    endpoint="http://localhost:9000",
    bucket="my-bucket",
    access_key="minioadmin",
    secret_key="minioadmin",
))
```

### DigitalOcean Spaces

```python
app.configure_storage(S3CompatibleBackend.digitalocean(
    region="nyc3",
    bucket="my-space",
    access_key="...",
    secret_key="...",
))
```

### Backblaze B2

```python
app.configure_storage(S3CompatibleBackend.backblaze(
    endpoint="https://s3.us-west-001.backblazeb2.com",
    bucket="my-bucket",
    key_id="...",
    app_key="...",
))
```

### Wasabi

```python
app.configure_storage(S3CompatibleBackend.wasabi(
    region="us-east-1",
    bucket="my-bucket",
    access_key="...",
    secret_key="...",
))
```

### Google Cloud Storage (S3 interop)

Requires HMAC credentials (not a service account key):

```python
app.configure_storage(S3CompatibleBackend.gcs(
    bucket="my-bucket",
    hmac_key="...",
    hmac_secret="...",
))
```

### Custom / generic

```python
app.configure_storage(S3CompatibleBackend(
    bucket="my-bucket",
    access_key="...",
    secret_key="...",
    endpoint_url="https://my-provider.example.com",
    region_name="us-east-1",
    key_prefix="uploads/",
    signed_url_expires=900,  # seconds for pre-signed URLs
))
```

## S3CompatibleBackend options

| Option | Default | Description |
|--------|---------|-------------|
| `bucket` | — | Bucket name |
| `access_key` | — | Access key ID |
| `secret_key` | — | Secret access key |
| `region_name` | `"us-east-1"` | AWS region |
| `endpoint_url` | `None` | Custom endpoint (for non-AWS providers) |
| `key_prefix` | `""` | Prefix prepended to all object keys |
| `signed_url_expires` | `900` | Pre-signed URL lifetime in seconds |
