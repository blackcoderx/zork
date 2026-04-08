from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from pydantic import BaseModel, Field as PydanticField, AnyUrl, create_model

from cinder.hooks.registry import HookRegistry
from cinder.hooks.runner import HookRunner


class Field:
    """Base class for collection field definitions."""

    def __init__(
        self,
        name: str,
        *,
        required: bool = False,
        default: Any = None,
        unique: bool = False,
    ):
        self.name = name
        self.required = required
        self.default = default
        self.unique = unique

    def sqlite_type(self) -> str:
        raise NotImplementedError

    def pydantic_field_info(self) -> tuple[type, Any]:
        """Return (python_type, FieldInfo) for Pydantic model creation."""
        raise NotImplementedError

    def column_sql(self) -> str:
        parts = [self.name, self.sqlite_type()]
        if self.required:
            parts.append("NOT NULL")
        if self.unique:
            parts.append("UNIQUE")
        return " ".join(parts)


class TextField(Field):
    def __init__(self, name: str, *, required: bool = False, default: Any = None,
                 unique: bool = False, min_length: int | None = None,
                 max_length: int | None = None):
        super().__init__(name, required=required, default=default, unique=unique)
        self.min_length = min_length
        self.max_length = max_length

    def sqlite_type(self) -> str:
        return "TEXT"

    def pydantic_field_info(self) -> tuple[type, Any]:
        kwargs = {}
        if self.min_length is not None:
            kwargs["min_length"] = self.min_length
        if self.max_length is not None:
            kwargs["max_length"] = self.max_length
        if self.required:
            return (str, PydanticField(**kwargs))
        if self.default is not None:
            return (str | None, PydanticField(default=self.default, **kwargs))
        return (str | None, PydanticField(default=None, **kwargs))


class IntField(Field):
    def __init__(self, name: str, *, required: bool = False, default: Any = None,
                 unique: bool = False, min_value: int | None = None,
                 max_value: int | None = None):
        super().__init__(name, required=required, default=default, unique=unique)
        self.min_value = min_value
        self.max_value = max_value

    def sqlite_type(self) -> str:
        return "INTEGER"

    def pydantic_field_info(self) -> tuple[type, Any]:
        kwargs = {}
        if self.min_value is not None:
            kwargs["ge"] = self.min_value
        if self.max_value is not None:
            kwargs["le"] = self.max_value
        if self.required:
            return (int, PydanticField(**kwargs))
        if self.default is not None:
            return (int | None, PydanticField(default=self.default, **kwargs))
        return (int | None, PydanticField(default=None, **kwargs))


class FloatField(Field):
    def __init__(self, name: str, *, required: bool = False, default: Any = None,
                 unique: bool = False, min_value: float | None = None,
                 max_value: float | None = None):
        super().__init__(name, required=required, default=default, unique=unique)
        self.min_value = min_value
        self.max_value = max_value

    def sqlite_type(self) -> str:
        return "REAL"

    def pydantic_field_info(self) -> tuple[type, Any]:
        kwargs = {}
        if self.min_value is not None:
            kwargs["ge"] = self.min_value
        if self.max_value is not None:
            kwargs["le"] = self.max_value
        if self.required:
            return (float, PydanticField(**kwargs))
        if self.default is not None:
            return (float | None, PydanticField(default=self.default, **kwargs))
        return (float | None, PydanticField(default=None, **kwargs))


class BoolField(Field):
    def sqlite_type(self) -> str:
        return "INTEGER"

    def pydantic_field_info(self) -> tuple[type, Any]:
        if self.required:
            return (bool, PydanticField())
        if self.default is not None:
            return (bool | None, PydanticField(default=self.default))
        return (bool | None, PydanticField(default=None))


class DateTimeField(Field):
    def __init__(self, name: str, *, required: bool = False, default: Any = None,
                 unique: bool = False, auto_now: bool = False):
        super().__init__(name, required=required, default=default, unique=unique)
        self.auto_now = auto_now

    def sqlite_type(self) -> str:
        return "TEXT"

    def pydantic_field_info(self) -> tuple[type, Any]:
        if self.auto_now:
            return (datetime | None, PydanticField(default=None))
        if self.required:
            return (datetime, PydanticField())
        return (datetime | None, PydanticField(default=self.default))


class URLField(Field):
    def sqlite_type(self) -> str:
        return "TEXT"

    def pydantic_field_info(self) -> tuple[type, Any]:
        if self.required:
            return (AnyUrl, PydanticField())
        if self.default is not None:
            return (AnyUrl | None, PydanticField(default=self.default))
        return (AnyUrl | None, PydanticField(default=None))


class JSONField(Field):
    def sqlite_type(self) -> str:
        return "TEXT"

    def pydantic_field_info(self) -> tuple[type, Any]:
        if self.required:
            return (Any, PydanticField())
        return (Any, PydanticField(default=self.default))


class FileField(Field):
    """A field that stores uploaded file metadata as JSON in SQLite.

    The actual file bytes are stored in a ``FileStorageBackend`` (local disk,
    S3, R2, MinIO, etc.). This field holds only the metadata dict (or list of
    dicts for ``multiple=True``).

    Cinder automatically generates ``POST``, ``GET``, and ``DELETE`` routes at
    ``/api/{collection}/{id}/files/{field_name}`` for every ``FileField``.

    Args:
        name: Field name (column name in SQLite).
        max_size: Maximum file size in bytes. Default 10 MB.
        allowed_types: List of MIME type patterns to accept, e.g.
            ``["image/*", "application/pdf"]``. Default ``["*/*"]`` (any).
        multiple: If ``True``, stores a list of files instead of one.
        public: If ``True``, the download route skips authentication.
            Use for publicly accessible files (avatars, cover images, etc.).
        required: If ``True``, the field cannot be ``null`` in JSON responses.
            Because files are uploaded via a separate route, this is rarely
            useful and defaults to ``False``.

    Example::

        class Posts(Collection):
            title = TextField(required=True)
            cover = FileField(max_size=5_000_000, allowed_types=["image/*"], public=True)
            attachments = FileField(multiple=True, allowed_types=["application/pdf"])
    """

    def __init__(
        self,
        name: str,
        *,
        max_size: int = 10_000_000,
        allowed_types: list[str] | None = None,
        multiple: bool = False,
        public: bool = False,
        required: bool = False,
    ) -> None:
        super().__init__(name, required=required, default=None, unique=False)
        self.max_size = max_size
        self.allowed_types: list[str] = allowed_types or ["*/*"]
        self.multiple = multiple
        self.public = public

    def sqlite_type(self) -> str:
        return "TEXT"

    def pydantic_field_info(self) -> tuple[type, Any]:
        # FileFields are read-only from the standard JSON body perspective.
        # Uploads happen via dedicated file routes, not the collection POST/PATCH.
        # We accept Any so existing metadata dicts pass through without rejection.
        return (Any, PydanticField(default=None))

    def serialize(self, value: Any) -> str | None:
        """Serialize metadata dict/list to a JSON string for SQLite storage."""
        if value is None:
            return None
        return json.dumps(value)

    def deserialize(self, value: str | None) -> Any:
        """Deserialize a JSON string from SQLite back to dict/list."""
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None

    def matches_mime(self, mime: str) -> bool:
        """Return True if ``mime`` matches any pattern in ``allowed_types``."""
        for pattern in self.allowed_types:
            if pattern == "*/*":
                return True
            if pattern.endswith("/*"):
                if mime.startswith(pattern[:-2]):
                    return True
            elif pattern == mime:
                return True
        return False


class RelationField(Field):
    def __init__(self, name: str, *, collection: str, required: bool = False,
                 unique: bool = False):
        super().__init__(name, required=required, default=None, unique=unique)
        self.collection = collection

    def sqlite_type(self) -> str:
        return "TEXT"

    def pydantic_field_info(self) -> tuple[type, Any]:
        if self.required:
            return (str, PydanticField())
        return (str | None, PydanticField(default=None))


class Collection:
    """A named schema that Cinder turns into a full CRUD API."""

    def __init__(self, name: str, fields: list[Field]):
        self.name = name
        self.fields = fields
        # Each collection starts with its own registry/runner so it is
        # usable standalone (tests, scripts). When the collection is
        # registered on a Cinder app, ``bind_registry`` swaps in the app's
        # shared registry and migrates any pre-registered handlers so that
        # app-level, collection-level and auth-level hooks all live in the
        # same place — namespaced purely by event string.
        self._registry: HookRegistry = HookRegistry()
        self._runner: HookRunner = HookRunner(self._registry)

    def bind_registry(self, registry: HookRegistry, runner: HookRunner) -> None:
        """Swap in a shared registry, migrating any existing handlers."""
        if registry is self._registry:
            return
        for event, handlers in self._registry._hooks.items():
            for h in handlers:
                registry.on(event, h)
        self._registry = registry
        self._runner = runner

    def on(self, event: str, handler: Callable | None = None):
        """Register a hook handler for an event on this collection.

        The event is namespaced as ``{collection}:{event}`` (e.g.
        ``"before_create"`` becomes ``"posts:before_create"``). Both
        built-in lifecycle events and arbitrary custom events use the same
        method — any string is a valid event name.

        Usable as a direct call::

            posts.on("before_create", add_slug)

        ...or as a decorator::

            @posts.on("before_create")
            async def add_slug(data, ctx):
                data["slug"] = slugify(data["title"])
                return data
        """
        full = f"{self.name}:{event}"
        if handler is None:
            def decorator(fn: Callable) -> Callable:
                self._registry.on(full, fn)
                return fn
            return decorator
        self._registry.on(full, handler)
        return handler

    async def fire(self, event: str, payload: Any, ctx: Any) -> Any:
        """Fire an event on this collection — built-in or custom.

        Equivalent to ``runner.fire(f"{collection}:{event}", ...)``. Firing
        an event with no registered handlers is a no-op.
        """
        return await self._runner.fire(f"{self.name}:{event}", payload, ctx)

    def build_create_table_sql(self) -> str:
        """Generate CREATE TABLE SQL for this collection."""
        columns = [
            "id TEXT PRIMARY KEY",
        ]
        for field in self.fields:
            columns.append(field.column_sql())
        columns.append("created_at TEXT NOT NULL")
        columns.append("updated_at TEXT NOT NULL")
        col_str = ", ".join(columns)
        return f"CREATE TABLE IF NOT EXISTS {self.name} ({col_str})"

    def build_pydantic_model(self) -> type[BaseModel]:
        """Dynamically create a Pydantic model for input validation."""
        field_definitions: dict[str, Any] = {}
        for field in self.fields:
            python_type, field_info = field.pydantic_field_info()
            field_definitions[field.name] = (python_type, field_info)
        model = create_model(
            f"{self.name.title()}Model",
            **field_definitions,
        )
        return model
