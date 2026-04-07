from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from cinder.collections.schema import Collection, BoolField, DateTimeField, JSONField
from cinder.db.connection import Database
from cinder.errors import CANCEL_DELETE_MESSAGE, CinderError
from cinder.hooks.context import CinderContext

logger = logging.getLogger("cinder.collections.store")


class CollectionStore:
    """Handles SQLite CRUD operations and schema synchronization for collections."""

    def __init__(self, db: Database):
        self.db = db

    async def sync_schema(self, collection: Collection) -> None:
        table_exists = await self.db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (collection.name,),
        )
        if not table_exists:
            sql = collection.build_create_table_sql()
            await self.db.execute(sql)
            return

        existing_cols = await self.db.fetch_all(
            f"PRAGMA table_info({collection.name})"
        )
        existing_names = {col["name"] for col in existing_cols}
        schema_names = {f.name for f in collection.fields}
        schema_names.update({"id", "created_at", "updated_at"})

        for field in collection.fields:
            if field.name not in existing_names:
                col_sql = field.column_sql()
                await self.db.execute(
                    f"ALTER TABLE {collection.name} ADD COLUMN {col_sql}"
                )
                logger.info(f"Added column '{field.name}' to table '{collection.name}'")

        for col_name in existing_names:
            if col_name not in schema_names:
                logger.warning(
                    f"Column '{col_name}' exists in table '{collection.name}' "
                    f"but is not in the schema. It will NOT be dropped."
                )

    async def create(
        self, collection: Collection, data: dict, ctx: CinderContext | None = None
    ) -> dict:
        ctx = ctx or CinderContext(collection=collection.name, operation="create")
        data = await collection._runner.run(
            f"{collection.name}:before_create", data, ctx
        )

        model = collection.build_pydantic_model()
        validated = model(**data)
        record = validated.model_dump()

        for field in collection.fields:
            if isinstance(field, BoolField) and record.get(field.name) is not None:
                record[field.name] = int(record[field.name])
            if isinstance(field, JSONField) and record.get(field.name) is not None:
                record[field.name] = json.dumps(record[field.name])
            if isinstance(field, DateTimeField) and field.auto_now:
                record[field.name] = datetime.now(timezone.utc).isoformat()

        for key, value in record.items():
            if hasattr(value, "__str__") and not isinstance(value, (str, int, float, bool, type(None))):
                record[key] = str(value)

        now = datetime.now(timezone.utc).isoformat()
        record["id"] = str(uuid.uuid4())
        record["created_at"] = now
        record["updated_at"] = now

        columns = ", ".join(record.keys())
        placeholders = ", ".join("?" for _ in record)
        values = tuple(record.values())

        await self.db.execute(
            f"INSERT INTO {collection.name} ({columns}) VALUES ({placeholders})",
            values,
        )

        saved = self._deserialize(collection, record)
        await collection._runner.run(
            f"{collection.name}:after_create", saved, ctx
        )
        return saved

    async def get(
        self, collection: Collection, id: str, ctx: CinderContext | None = None
    ) -> dict | None:
        ctx = ctx or CinderContext(collection=collection.name, operation="read")
        id = await collection._runner.run(
            f"{collection.name}:before_read", id, ctx
        )
        row = await self.db.fetch_one(
            f"SELECT * FROM {collection.name} WHERE id = ?", (id,)
        )
        if row is None:
            return None
        record = self._deserialize(collection, dict(row))
        record = await collection._runner.run(
            f"{collection.name}:after_read", record, ctx
        )
        return record

    async def list(
        self,
        collection: Collection,
        *,
        filters: dict[str, Any] | None = None,
        order_by: str = "created_at",
        limit: int = 20,
        offset: int = 0,
        ctx: CinderContext | None = None,
    ) -> tuple[list[dict], int]:
        ctx = ctx or CinderContext(collection=collection.name, operation="list")
        query_desc: dict[str, Any] = {
            "filters": dict(filters) if filters else {},
            "order_by": order_by,
            "limit": limit,
            "offset": offset,
        }
        query_desc = await collection._runner.run(
            f"{collection.name}:before_list", query_desc, ctx
        )
        filters = query_desc.get("filters") or None
        order_by = query_desc.get("order_by", order_by)
        limit = query_desc.get("limit", limit)
        offset = query_desc.get("offset", offset)

        where_clauses: list[str] = []
        params: list[Any] = []

        if filters:
            for key, value in filters.items():
                where_clauses.append(f"{key} = ?")
                params.append(value)

        where_sql = ""
        if where_clauses:
            where_sql = " WHERE " + " AND ".join(where_clauses)

        count_row = await self.db.fetch_one(
            f"SELECT COUNT(*) as total FROM {collection.name}{where_sql}",
            tuple(params),
        )
        total = count_row["total"] if count_row else 0

        query = (
            f"SELECT * FROM {collection.name}{where_sql} "
            f"ORDER BY {order_by} LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        rows = await self.db.fetch_all(query, tuple(params))

        items = [self._deserialize(collection, dict(r)) for r in rows]
        items = await collection._runner.run(
            f"{collection.name}:after_list", items, ctx
        )
        return items, total

    async def update(
        self,
        collection: Collection,
        id: str,
        data: dict,
        ctx: CinderContext | None = None,
    ) -> dict | None:
        ctx = ctx or CinderContext(collection=collection.name, operation="update")
        existing = await self._raw_get(collection, id)
        if existing is None:
            return None

        data = await collection._runner.run(
            f"{collection.name}:before_update", data, ctx
        )

        if data:
            model = collection.build_pydantic_model()
            merged = {**existing, **data}
            for key in ("id", "created_at", "updated_at"):
                merged.pop(key, None)
            validated = model(**merged)
            validated_data = validated.model_dump()
            update_values: dict[str, Any] = {}
            for key in data:
                if key in validated_data:
                    update_values[key] = validated_data[key]
        else:
            update_values = {}

        for field in collection.fields:
            if field.name in update_values:
                if isinstance(field, BoolField) and update_values[field.name] is not None:
                    update_values[field.name] = int(update_values[field.name])
                if isinstance(field, JSONField) and update_values[field.name] is not None:
                    update_values[field.name] = json.dumps(update_values[field.name])
            if isinstance(field, DateTimeField) and field.auto_now:
                update_values[field.name] = datetime.now(timezone.utc).isoformat()

        for key, value in update_values.items():
            if hasattr(value, "__str__") and not isinstance(value, (str, int, float, bool, type(None))):
                update_values[key] = str(value)

        update_values["updated_at"] = datetime.now(timezone.utc).isoformat()

        set_clauses = ", ".join(f"{k} = ?" for k in update_values)
        params = list(update_values.values()) + [id]

        await self.db.execute(
            f"UPDATE {collection.name} SET {set_clauses} WHERE id = ?",
            tuple(params),
        )

        updated = await self._raw_get(collection, id)
        await collection._runner.run(
            f"{collection.name}:after_update", (updated, existing), ctx
        )
        return updated

    async def delete(
        self, collection: Collection, id: str, ctx: CinderContext | None = None
    ) -> bool:
        ctx = ctx or CinderContext(collection=collection.name, operation="delete")
        existing = await self._raw_get(collection, id)
        if existing is None:
            return False
        try:
            await collection._runner.run(
                f"{collection.name}:before_delete", existing, ctx
            )
        except CinderError as e:
            if e.message == CANCEL_DELETE_MESSAGE:
                # Soft-delete / handled manually — skip the DB delete but
                # report success to the caller.
                return True
            raise
        await self.db.execute(
            f"DELETE FROM {collection.name} WHERE id = ?", (id,)
        )
        await collection._runner.run(
            f"{collection.name}:after_delete", existing, ctx
        )
        return True

    async def _raw_get(self, collection: Collection, id: str) -> dict | None:
        """Internal fetch that bypasses read hooks."""
        row = await self.db.fetch_one(
            f"SELECT * FROM {collection.name} WHERE id = ?", (id,)
        )
        if row is None:
            return None
        return self._deserialize(collection, dict(row))

    def _deserialize(self, collection: Collection, record: dict) -> dict:
        for field in collection.fields:
            val = record.get(field.name)
            if val is None:
                continue
            if isinstance(field, BoolField):
                record[field.name] = bool(val)
            if isinstance(field, JSONField) and isinstance(val, str):
                try:
                    record[field.name] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
        return record
