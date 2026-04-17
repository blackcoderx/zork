from __future__ import annotations

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from zork.collections.schema import Collection, FileField, RelationField
from zork.collections.store import CollectionStore
from zork.errors import ZorkError
from zork.hooks.context import ZorkContext


def build_collection_routes(
    collections: dict[str, tuple[Collection, dict[str, str]]],
    store: CollectionStore,
    storage_backend=None,
    prefix: str | None = None,
) -> list[Route]:
    """Build routes for all collections.

    Args:
        collections: Dict of collection name -> (Collection, auth_rules)
        store: CollectionStore instance
        storage_backend: Optional storage backend for FileField
        prefix: URL prefix for routes (e.g., "/api/v1"). If None, uses "/api".
    """
    route_prefix = prefix or "/api"
    routes: list[Route] = []
    for name, (collection, auth_rules) in collections.items():
        routes.extend(
            _routes_for_collection(
                collection,
                auth_rules,
                store,
                collections,
                storage_backend,
                route_prefix,
            )
        )
    return routes


def _check_auth(request: Request, rule: str) -> None:
    if rule == "public":
        return
    user = getattr(request.state, "user", None)
    if user is None:
        raise ZorkError(401, "Authentication required")
    if rule == "authenticated":
        return
    if rule == "admin":
        if user.get("role") != "admin":
            raise ZorkError(403, "Admin access required")
        return
    if rule == "owner":
        return  # per-record check done in handlers


def _check_owner(request: Request, record: dict) -> None:
    user = getattr(request.state, "user", None)
    if user is None:
        raise ZorkError(401, "Authentication required")
    if record.get("created_by") != user.get("id"):
        raise ZorkError(403, "You do not have permission to access this record")


def _routes_for_collection(
    collection: Collection,
    auth_rules: dict[str, str],
    store: CollectionStore,
    all_collections: dict[str, tuple[Collection, dict[str, str]]],
    storage_backend=None,
    prefix: str = "/api",
) -> list[Route]:
    read_rule = auth_rules.get("read", "public")
    write_rule = auth_rules.get("write", "public")

    async def list_records(request: Request) -> JSONResponse:
        _check_auth(request, read_rule)
        params = dict(request.query_params)
        limit = int(params.pop("limit", "20"))
        offset = int(params.pop("offset", "0"))
        order_by = params.pop("order_by", "created_at")
        expand_fields = (
            params.pop("expand", "").split(",") if "expand" in params else []
        )
        filters = params if params else None
        ctx = ZorkContext.from_request(
            request, collection=collection.name, operation="list"
        )
        items, total = await store.list(
            collection,
            filters=filters,
            order_by=order_by,
            limit=limit,
            offset=offset,
            ctx=ctx,
        )
        if read_rule == "owner":
            user = getattr(request.state, "user", None)
            if user is None:
                raise ZorkError(401, "Authentication required")
            items = [i for i in items if i.get("created_by") == user["id"]]
            total = len(items)
        if expand_fields:
            for item in items:
                item["expand"] = {}
                for field_name in expand_fields:
                    await _expand_field(
                        item, field_name, collection, store, all_collections
                    )
        return JSONResponse(
            {
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

    async def get_record(request: Request) -> JSONResponse:
        _check_auth(request, read_rule)
        record_id = request.path_params["id"]
        ctx = ZorkContext.from_request(
            request, collection=collection.name, operation="read"
        )
        record = await store.get(collection, record_id, ctx=ctx)
        if record is None:
            raise ZorkError(404, "Record not found")
        if read_rule == "owner":
            _check_owner(request, record)
        expand_param = request.query_params.get("expand", "")
        if expand_param:
            record["expand"] = {}
            for field_name in expand_param.split(","):
                await _expand_field(
                    record, field_name, collection, store, all_collections
                )
        return JSONResponse(record)

    async def create_record(request: Request) -> JSONResponse:
        _check_auth(request, write_rule)
        body = await request.json()
        if write_rule == "owner" or read_rule == "owner":
            user = getattr(request.state, "user", None)
            if user:
                body["created_by"] = user["id"]
        ctx = ZorkContext.from_request(
            request, collection=collection.name, operation="create"
        )
        try:
            record = await store.create(collection, body, ctx=ctx)
        except ValidationError as e:
            raise ZorkError(400, str(e))
        return JSONResponse(record, status_code=201)

    async def update_record(request: Request) -> JSONResponse:
        _check_auth(request, write_rule)
        record_id = request.path_params["id"]
        if write_rule == "owner":
            existing = await store.get(collection, record_id)
            if existing is None:
                raise ZorkError(404, "Record not found")
            _check_owner(request, existing)
        body = await request.json()
        ctx = ZorkContext.from_request(
            request, collection=collection.name, operation="update"
        )
        try:
            record = await store.update(collection, record_id, body, ctx=ctx)
        except ValidationError as e:
            raise ZorkError(400, str(e))
        if record is None:
            raise ZorkError(404, "Record not found")
        return JSONResponse(record)

    async def delete_record(request: Request) -> JSONResponse:
        _check_auth(request, write_rule)
        record_id = request.path_params["id"]
        if write_rule == "owner":
            existing = await store.get(collection, record_id)
            if existing is None:
                raise ZorkError(404, "Record not found")
            _check_owner(request, existing)
        ctx = ZorkContext.from_request(
            request, collection=collection.name, operation="delete"
        )
        deleted = await store.delete(collection, record_id, ctx=ctx)
        if not deleted:
            raise ZorkError(404, "Record not found")
        return JSONResponse({"message": "Record deleted"})

    collection_path = f"{prefix}/{collection.name}"
    id_path = f"{prefix}/{collection.name}/{{id}}"

    routes = [
        Route(collection_path, list_records, methods=["GET"]),
        Route(id_path, get_record, methods=["GET"]),
        Route(collection_path, create_record, methods=["POST"]),
        Route(id_path, update_record, methods=["PATCH"]),
        Route(id_path, delete_record, methods=["DELETE"]),
    ]

    # Auto-generate file routes for every FileField on this collection
    if storage_backend is not None:
        from zork.storage.routes import (
            make_delete_handler,
            make_download_handler,
            make_upload_handler,
        )

        for field in collection.fields:
            if isinstance(field, FileField):
                field_name = field.name
                path = f"{prefix}/{collection.name}/{{id}}/files/{field_name}"
                routes.extend(
                    [
                        Route(
                            path,
                            make_upload_handler(
                                collection,
                                field_name,
                                field,
                                store,
                                storage_backend,
                                write_rule,
                            ),
                            methods=["POST"],
                        ),
                        Route(
                            path,
                            make_download_handler(
                                collection,
                                field_name,
                                field,
                                store,
                                storage_backend,
                                read_rule,
                            ),
                            methods=["GET"],
                        ),
                        Route(
                            path,
                            make_delete_handler(
                                collection,
                                field_name,
                                field,
                                store,
                                storage_backend,
                                write_rule,
                            ),
                            methods=["DELETE"],
                        ),
                    ]
                )

    return routes


async def _expand_field(
    record: dict,
    field_name: str,
    collection: Collection,
    store: CollectionStore,
    all_collections: dict[str, tuple[Collection, dict[str, str]]],
) -> None:
    field_name = field_name.strip()
    if not field_name:
        return
    relation_field = None
    for f in collection.fields:
        if f.name == field_name and isinstance(f, RelationField):
            relation_field = f
            break
    if relation_field is None:
        return
    related_id = record.get(field_name)
    if related_id is None:
        return
    target_name = relation_field.collection
    if target_name not in all_collections:
        return
    target_collection, _ = all_collections[target_name]
    related_record = await store.get(target_collection, related_id)
    if related_record:
        if "expand" not in record:
            record["expand"] = {}
        record["expand"][field_name] = related_record
