"""File upload / download / delete route handlers for Cinder collections.

Each public function is a *factory* that captures the collection, field, store,
and backend in a closure and returns a Starlette-compatible async callable.
The factory pattern keeps the signatures clean and avoids global state.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, RedirectResponse

from cinder.errors import CinderError
from cinder.hooks.context import CinderContext

from .keys import generate_key

if TYPE_CHECKING:
    from cinder.collections.schema import Collection, FileField
    from cinder.collections.store import CollectionStore
    from .backends import FileStorageBackend

logger = logging.getLogger("cinder.storage")

# Magic bytes map: MIME type prefix → (offset, bytes_sequence)
# Used to validate actual file content against the declared MIME type.
_MAGIC: list[tuple[str, int, bytes]] = [
    ("image/jpeg", 0, b"\xff\xd8\xff"),
    ("image/png", 0, b"\x89PNG\r\n\x1a\n"),
    ("image/gif", 0, b"GIF87a"),
    ("image/gif", 0, b"GIF89a"),
    ("image/webp", 8, b"WEBP"),
    ("image/bmp", 0, b"BM"),
    ("image/tiff", 0, b"II\x2a\x00"),
    ("image/tiff", 0, b"MM\x00\x2a"),
    ("application/pdf", 0, b"%PDF"),
    ("application/zip", 0, b"PK\x03\x04"),
    ("application/zip", 0, b"PK\x05\x06"),
    ("application/gzip", 0, b"\x1f\x8b"),
    ("video/mp4", 4, b"ftyp"),
    ("audio/mpeg", 0, b"\xff\xfb"),
    ("audio/mpeg", 0, b"\xff\xf3"),
    ("audio/mpeg", 0, b"ID3"),
]

_KNOWN_BINARY_PREFIXES = {
    "image/", "video/", "audio/", "application/pdf",
    "application/zip", "application/gzip",
}


def _sniff_mime(header: bytes) -> str | None:
    """Attempt to detect MIME type from the first 512 bytes of a file."""
    for mime, offset, magic in _MAGIC:
        end = offset + len(magic)
        if len(header) >= end and header[offset:end] == magic:
            return mime
    return None


def _mime_matches_header(sniffed: str | None, declared: str) -> bool:
    """Return True if the sniffed MIME is compatible with the declared one.

    We only reject when we *positively identify* a mismatch. Unknown/text
    files that don't match any magic bytes pass through (sniffed is None).
    """
    if sniffed is None:
        return True  # can't detect → give benefit of the doubt
    declared_main = declared.split("/")[0]
    sniffed_main = sniffed.split("/")[0]
    # Must match at least the top-level type
    if declared_main != sniffed_main:
        return False
    return True


def _check_auth(request: Request, rule: str) -> None:
    """Reuse the same auth check logic as the collection router."""
    if rule == "public":
        return
    user = getattr(request.state, "user", None)
    if user is None:
        raise CinderError(401, "Authentication required")
    if rule == "admin" and user.get("role") != "admin":
        raise CinderError(403, "Admin access required")


def make_upload_handler(
    collection: "Collection",
    field_name: str,
    field: "FileField",
    store: "CollectionStore",
    backend: "FileStorageBackend",
    write_rule: str,
) -> callable:
    """Return an async handler for ``POST /api/{collection}/{id}/files/{field}``."""

    async def upload_file(request: Request) -> JSONResponse:
        # 1. Auth check (public fields still require write auth for uploads)
        _check_auth(request, write_rule)

        record_id = request.path_params["id"]

        # 2. Content-type must be multipart/form-data
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" not in content_type:
            raise CinderError(415, "File upload requires multipart/form-data")

        # 3. Parse form
        try:
            form = await request.form()
        except Exception as exc:
            raise CinderError(400, f"Failed to parse multipart form: {exc}") from exc

        upload = form.get("file")
        if upload is None:
            raise CinderError(400, "Missing 'file' field in multipart form")

        filename = getattr(upload, "filename", None) or "upload"
        declared_content_type = getattr(upload, "content_type", None) or "application/octet-stream"

        # 4. Read with size guard — read in chunks, abort if max_size exceeded
        _CHUNK = 65536  # 64 KB
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await upload.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > field.max_size:
                raise CinderError(
                    413,
                    f"File exceeds maximum allowed size of {field.max_size} bytes",
                )
            chunks.append(chunk)
        data = b"".join(chunks)

        # 5. MIME validation: header check + magic bytes
        if not field.matches_mime(declared_content_type):
            raise CinderError(
                422,
                f"File type '{declared_content_type}' is not allowed. "
                f"Accepted: {', '.join(field.allowed_types)}",
            )
        header_bytes = data[:512]
        sniffed = _sniff_mime(header_bytes)
        if not _mime_matches_header(sniffed, declared_content_type):
            raise CinderError(
                422,
                f"File content does not match declared MIME type '{declared_content_type}'",
            )
        # Use sniffed MIME if available (more reliable than the browser declaration)
        effective_mime = sniffed or declared_content_type

        # 6. Fetch the existing record
        ctx = CinderContext.from_request(request, collection=collection.name, operation="update")
        record = await store.get(collection, record_id, ctx=ctx)
        if record is None:
            raise CinderError(404, "Record not found")

        # 7. If single-file mode, delete the old file from the backend first
        existing_meta = record.get(field_name)
        if not field.multiple and existing_meta:
            old_key = existing_meta.get("key") if isinstance(existing_meta, dict) else None
            if old_key:
                try:
                    await backend.delete(old_key)
                except Exception:
                    pass  # Don't fail the upload if cleanup fails

        # 8. Generate storage key and persist
        key = generate_key(collection.name, record_id, field_name, filename)
        await backend.put(key, data, effective_mime)

        new_meta = {
            "key": key,
            "name": filename,
            "size": len(data),
            "mime": effective_mime,
        }

        # 9. Update SQLite metadata
        if field.multiple:
            current = existing_meta if isinstance(existing_meta, list) else []
            updated_meta = current + [new_meta]
        else:
            updated_meta = new_meta

        updated_record = await store.update(
            collection, record_id, {field_name: updated_meta}, ctx=ctx
        )
        if updated_record is None:
            raise CinderError(500, "Failed to update record metadata")
        return JSONResponse(updated_record, status_code=201)

    return upload_file


def make_download_handler(
    collection: "Collection",
    field_name: str,
    field: "FileField",
    store: "CollectionStore",
    backend: "FileStorageBackend",
    read_rule: str,
) -> callable:
    """Return an async handler for ``GET /api/{collection}/{id}/files/{field}``."""

    async def download_file(request: Request) -> Response:
        # 1. Auth check — FileField.public=True allows unauthenticated download;
        # FileField.public=False always requires at least authentication,
        # regardless of the collection's read rule (which controls record reads,
        # not file downloads).
        if not field.public:
            effective_rule = read_rule if read_rule != "public" else "authenticated"
            _check_auth(request, effective_rule)

        record_id = request.path_params["id"]
        ctx = CinderContext.from_request(request, collection=collection.name, operation="read")
        record = await store.get(collection, record_id, ctx=ctx)
        if record is None:
            raise CinderError(404, "Record not found")

        # 2. Extract metadata
        meta = record.get(field_name)
        if not meta:
            raise CinderError(404, "No file uploaded for this field")

        if field.multiple:
            index_param = request.query_params.get("index")
            if index_param is None:
                raise CinderError(400, "?index=N is required for multi-file fields")
            try:
                index = int(index_param)
            except ValueError:
                raise CinderError(400, "?index must be an integer")
            if not isinstance(meta, list) or index < 0 or index >= len(meta):
                raise CinderError(404, f"No file at index {index}")
            file_meta = meta[index]
        else:
            file_meta = meta if isinstance(meta, dict) else None
            if not file_meta:
                raise CinderError(404, "No file uploaded for this field")

        key = file_meta.get("key")
        if not key:
            raise CinderError(500, "File metadata is corrupt (missing key)")

        original_name = file_meta.get("name", "download")
        stored_mime = file_meta.get("mime", "application/octet-stream")

        # 3. Resolve URL strategy
        if field.public:
            resolved_url = await backend.url(key)
        else:
            resolved_url = await backend.signed_url(key)

        if resolved_url:
            return RedirectResponse(url=resolved_url, status_code=302)

        # 4. Proxy the bytes through Cinder
        try:
            data, content_type = await backend.get(key)
        except FileNotFoundError:
            raise CinderError(404, "File not found in storage backend")

        effective_mime = stored_mime or content_type
        return Response(
            content=data,
            media_type=effective_mime,
            headers={
                "Content-Disposition": f'attachment; filename="{original_name}"',
                "Content-Length": str(len(data)),
            },
        )

    return download_file


def make_delete_handler(
    collection: "Collection",
    field_name: str,
    field: "FileField",
    store: "CollectionStore",
    backend: "FileStorageBackend",
    write_rule: str,
) -> callable:
    """Return an async handler for ``DELETE /api/{collection}/{id}/files/{field}``."""

    async def delete_file(request: Request) -> JSONResponse:
        # Auth always required for delete, even for public fields
        _check_auth(request, write_rule)

        record_id = request.path_params["id"]
        ctx = CinderContext.from_request(request, collection=collection.name, operation="update")
        record = await store.get(collection, record_id, ctx=ctx)
        if record is None:
            raise CinderError(404, "Record not found")

        meta = record.get(field_name)
        if not meta:
            raise CinderError(404, "No file to delete for this field")

        if field.multiple:
            delete_all = request.query_params.get("all", "").lower() == "true"
            index_param = request.query_params.get("index")

            if delete_all:
                # Delete all files in the list
                if isinstance(meta, list):
                    for entry in meta:
                        if isinstance(entry, dict) and entry.get("key"):
                            try:
                                await backend.delete(entry["key"])
                            except Exception:
                                pass
                updated_meta = None
            elif index_param is not None:
                try:
                    index = int(index_param)
                except ValueError:
                    raise CinderError(400, "?index must be an integer")
                if not isinstance(meta, list) or index < 0 or index >= len(meta):
                    raise CinderError(404, f"No file at index {index}")
                entry = meta[index]
                if isinstance(entry, dict) and entry.get("key"):
                    try:
                        await backend.delete(entry["key"])
                    except Exception:
                        pass
                updated_meta = [m for i, m in enumerate(meta) if i != index]
            else:
                raise CinderError(400, "Provide ?index=N or ?all=true for multi-file fields")
        else:
            # Single file
            key = meta.get("key") if isinstance(meta, dict) else None
            if key:
                try:
                    await backend.delete(key)
                except Exception:
                    pass
            updated_meta = None

        updated_record = await store.update(
            collection, record_id, {field_name: updated_meta}, ctx=ctx
        )
        if updated_record is None:
            raise CinderError(500, "Failed to update record metadata")
        return JSONResponse(updated_record)

    return delete_file
