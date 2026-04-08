from __future__ import annotations

import asyncio
import functools
from typing import Any

from .backends import FileStorageBackend


class S3CompatibleBackend(FileStorageBackend):
    """File storage backed by any S3-compatible object store.

    Uses boto3 (sync) executed in a thread pool so Cinder's async event loop
    is never blocked. Requires the ``s3`` optional dependency::

        pip install cinder[s3]
        # or
        uv add cinder[s3]

    **Quick start — provider presets:**

    .. code-block:: python

        # AWS S3
        app.configure_storage(S3CompatibleBackend.aws("my-bucket", KEY, SECRET))

        # Cloudflare R2
        app.configure_storage(S3CompatibleBackend.r2(ACCOUNT_ID, "my-bucket", KEY, SECRET))

        # MinIO
        app.configure_storage(S3CompatibleBackend.minio("http://localhost:9000", "my-bucket", KEY, SECRET))

        # Backblaze B2
        app.configure_storage(S3CompatibleBackend.backblaze("https://s3.us-west-001.backblazeb2.com", "my-bucket", KEY_ID, APP_KEY))

        # DigitalOcean Spaces
        app.configure_storage(S3CompatibleBackend.digitalocean("nyc3", "my-space", KEY, SECRET))

        # Wasabi
        app.configure_storage(S3CompatibleBackend.wasabi("us-east-1", "my-bucket", KEY, SECRET))

        # Google Cloud Storage (S3 interop — requires HMAC credentials)
        app.configure_storage(S3CompatibleBackend.gcs("my-bucket", HMAC_KEY, HMAC_SECRET))

    **Custom / generic:**

    .. code-block:: python

        app.configure_storage(S3CompatibleBackend(
            bucket="my-bucket",
            access_key=KEY,
            secret_key=SECRET,
            endpoint_url="https://my-provider.example.com",
            region_name="us-east-1",
        ))
    """

    def __init__(
        self,
        bucket: str,
        access_key: str,
        secret_key: str,
        region_name: str = "us-east-1",
        endpoint_url: str | None = None,
        key_prefix: str = "",
        signed_url_expires: int = 900,
        extra_config: dict[str, Any] | None = None,
    ) -> None:
        self._bucket = bucket
        self._access_key = access_key
        self._secret_key = secret_key
        self._region_name = region_name
        self._endpoint_url = endpoint_url
        self._key_prefix = key_prefix.rstrip("/")
        self._signed_url_expires = signed_url_expires
        self._extra_config = extra_config or {}
        self._client: Any = None  # lazy-initialised on first use

    # ------------------------------------------------------------------
    # Provider presets
    # ------------------------------------------------------------------

    @classmethod
    def aws(
        cls,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> "S3CompatibleBackend":
        """Amazon Web Services S3."""
        return cls(bucket=bucket, access_key=access_key, secret_key=secret_key, region_name=region)

    @classmethod
    def r2(
        cls,
        account_id: str,
        bucket: str,
        access_key: str,
        secret_key: str,
    ) -> "S3CompatibleBackend":
        """Cloudflare R2.

        ``account_id`` is the Cloudflare account ID (found in the R2 dashboard).
        """
        return cls(
            bucket=bucket,
            access_key=access_key,
            secret_key=secret_key,
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            region_name="auto",
        )

    @classmethod
    def minio(
        cls,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
    ) -> "S3CompatibleBackend":
        """MinIO.

        ``endpoint`` is the full MinIO server URL, e.g. ``http://localhost:9000``.
        """
        return cls(
            bucket=bucket,
            access_key=access_key,
            secret_key=secret_key,
            endpoint_url=endpoint,
            region_name="us-east-1",
            extra_config={"signature_version": "s3v4"},
        )

    @classmethod
    def backblaze(
        cls,
        endpoint: str,
        bucket: str,
        key_id: str,
        app_key: str,
    ) -> "S3CompatibleBackend":
        """Backblaze B2.

        ``endpoint`` is the S3-compatible endpoint from the B2 dashboard,
        e.g. ``https://s3.us-west-001.backblazeb2.com``.
        Region is extracted automatically from the endpoint hostname.
        """
        # Extract region from hostname: s3.<region>.backblazeb2.com
        try:
            host = endpoint.split("://", 1)[1].split("/")[0]  # e.g. s3.us-west-001.backblazeb2.com
            parts = host.split(".")
            region = parts[1] if len(parts) >= 3 else "us-west-001"
        except Exception:
            region = "us-west-001"
        return cls(
            bucket=bucket,
            access_key=key_id,
            secret_key=app_key,
            endpoint_url=endpoint,
            region_name=region,
        )

    @classmethod
    def digitalocean(
        cls,
        region: str,
        space: str,
        access_key: str,
        secret_key: str,
    ) -> "S3CompatibleBackend":
        """DigitalOcean Spaces.

        ``region`` is the DO datacenter region, e.g. ``nyc3``, ``sfo3``.
        ``space`` is the Space name (equivalent to an S3 bucket).
        """
        return cls(
            bucket=space,
            access_key=access_key,
            secret_key=secret_key,
            endpoint_url=f"https://{region}.digitaloceanspaces.com",
            region_name=region,
        )

    @classmethod
    def wasabi(
        cls,
        region: str,
        bucket: str,
        access_key: str,
        secret_key: str,
    ) -> "S3CompatibleBackend":
        """Wasabi Hot Cloud Storage.

        ``region`` is the Wasabi region, e.g. ``us-east-1``, ``eu-central-1``.
        """
        return cls(
            bucket=bucket,
            access_key=access_key,
            secret_key=secret_key,
            endpoint_url=f"https://s3.{region}.wasabisys.com",
            region_name=region,
        )

    @classmethod
    def gcs(
        cls,
        bucket: str,
        access_key: str,
        secret_key: str,
    ) -> "S3CompatibleBackend":
        """Google Cloud Storage via S3-compatible interoperability API.

        Requires GCS HMAC credentials (not a service account JSON key).
        Generate them at: Cloud Console → Storage → Settings → Interoperability.

        Note: Some advanced S3 features are unavailable via the GCS interop API.
        """
        return cls(
            bucket=bucket,
            access_key=access_key,
            secret_key=secret_key,
            endpoint_url="https://storage.googleapis.com",
            region_name="auto",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        """Lazily create and cache the boto3 S3 client."""
        if self._client is not None:
            return self._client
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for S3CompatibleBackend. "
                "Install it with: pip install cinder[s3]"
            ) from exc

        config_kwargs: dict[str, Any] = {}
        if "signature_version" in self._extra_config:
            config_kwargs["signature_version"] = self._extra_config["signature_version"]
        if "addressing_style" in self._extra_config:
            config_kwargs["s3"] = {"addressing_style": self._extra_config["addressing_style"]}

        client_kwargs: dict[str, Any] = {
            "service_name": "s3",
            "aws_access_key_id": self._access_key,
            "aws_secret_access_key": self._secret_key,
            "region_name": self._region_name,
        }
        if self._endpoint_url:
            client_kwargs["endpoint_url"] = self._endpoint_url
        if config_kwargs:
            client_kwargs["config"] = Config(**config_kwargs)

        self._client = boto3.client(**client_kwargs)
        return self._client

    def _prefixed(self, key: str) -> str:
        if self._key_prefix:
            return f"{self._key_prefix}/{key}"
        return key

    async def _run(self, func, *args, **kwargs):
        """Run a sync boto3 call in a thread pool to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))

    # ------------------------------------------------------------------
    # FileStorageBackend interface
    # ------------------------------------------------------------------

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        client = self._get_client()
        await self._run(
            client.put_object,
            Bucket=self._bucket,
            Key=self._prefixed(key),
            Body=data,
            ContentType=content_type,
        )

    async def get(self, key: str) -> tuple[bytes, str]:
        client = self._get_client()
        try:
            response = await self._run(
                client.get_object,
                Bucket=self._bucket,
                Key=self._prefixed(key),
            )
        except client.exceptions.NoSuchKey:
            raise FileNotFoundError(f"No file at key '{key}'")
        except Exception as exc:
            # Re-raise boto3 ClientError as FileNotFoundError for 404s
            error_code = getattr(getattr(exc, "response", {}).get("Error", {}), "get", lambda k, d=None: d)("Code")
            if error_code == "NoSuchKey":
                raise FileNotFoundError(f"No file at key '{key}'") from exc
            raise
        body = await self._run(response["Body"].read)
        content_type = response.get("ContentType", "application/octet-stream")
        return body, content_type

    async def delete(self, key: str) -> None:
        client = self._get_client()
        # S3 delete_object is idempotent — no error if key doesn't exist
        await self._run(
            client.delete_object,
            Bucket=self._bucket,
            Key=self._prefixed(key),
        )

    async def signed_url(self, key: str, expires_in: int = 900) -> str | None:
        client = self._get_client()
        try:
            url = await self._run(
                client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self._bucket, "Key": self._prefixed(key)},
                ExpiresIn=expires_in,
            )
            return url
        except Exception:
            return None

    async def url(self, key: str) -> str | None:
        """Return a permanent public URL if the bucket/object is publicly accessible.

        Returns ``None`` by default — override or subclass if your bucket has a
        public policy and you want to skip signing overhead.
        """
        return None
