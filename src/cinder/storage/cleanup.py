"""Orphan file cleanup for Cinder collections.

When a record is deleted, any files stored in its ``FileField`` columns must
also be removed from the storage backend. This module wires ``after_delete``
hooks for every collection that has at least one ``FileField``.

Cleanup failures are logged but never re-raised — a backend error must not
prevent the record deletion from succeeding.

Usage (called from ``app.py`` during ``build()``)::

    from cinder.storage.cleanup import install_file_cleanup
    install_file_cleanup(registry, backend, collections)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cinder.hooks.registry import HookRegistry

if TYPE_CHECKING:
    from cinder.collections.schema import Collection, FileField
    from .backends import FileStorageBackend

logger = logging.getLogger("cinder.storage.cleanup")


def install_file_cleanup(
    registry: HookRegistry,
    backend: "FileStorageBackend",
    collections: dict,
) -> None:
    """Register after_delete cleanup hooks for collections with FileFields."""
    from cinder.collections.schema import FileField as _FileField

    for name, entry in collections.items():
        # collections dict is {name: (Collection, auth_rules)} from app.py
        collection: Collection = entry[0] if isinstance(entry, tuple) else entry
        file_fields: list[tuple[str, FileField]] = [
            (f.name, f)
            for f in collection.fields
            if isinstance(f, _FileField)
        ]
        if file_fields:
            _register_cleanup_hooks(registry, backend, name, file_fields)


def _register_cleanup_hooks(
    registry: HookRegistry,
    backend: "FileStorageBackend",
    collection_name: str,
    file_fields: list[tuple[str, "FileField"]],
) -> None:
    async def after_delete(record, ctx) -> None:
        if not isinstance(record, dict):
            return
        for field_name, field in file_fields:
            metadata = record.get(field_name)
            if not metadata:
                continue
            entries = metadata if field.multiple else [metadata]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                key = entry.get("key")
                if not key:
                    continue
                try:
                    await backend.delete(key)
                    logger.debug(
                        "Cleaned up file key '%s' for deleted record in '%s'",
                        key,
                        collection_name,
                    )
                except Exception:
                    logger.exception(
                        "File cleanup failed for key '%s' in collection '%s'",
                        key,
                        collection_name,
                    )

    registry.on(f"{collection_name}:after_delete", after_delete)
