from __future__ import annotations

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from zork.collections.schema import Collection, FileField, RelationField
from zork.collections.store import CollectionStore
from zork.errors import ZorkError
from zork.hooks.context import ZorkContext
from zork.response import ResponseModel


def _transform_response(data, collection: Collection, request: Request) -> dict | list[dict]:
    """Transform response data according to collection's response config.

    Supports query parameter overrides:
    - ?fields=id,name,email - include only these fields
    - ?exclude=password,token - exclude these fields
    - ?exclude_none=true - exclude None values

    Args:
        data: Single record dict or list of records
        collection: The collection to get config from
        request: The request to extract query params from

    Returns:
        Transformed data
    """
    if not collection.has_response_config():
        return data

    config = collection.get_response_config()
    query_params = dict(request.query_params)

    include = config["include"]
    exclude = set(config["exclude"]) | config["hidden_fields"]
    exclude_none = config["exclude_none"]
    exclude_unset = config["exclude_unset"]
    exclude_defaults = config["exclude_defaults"]
    by_alias = config["by_alias"]
    model = config["model"]

    if "fields" in query_params:
        include = set(query_params["fields"].split(","))
    if "exclude" in query_params:
        exclude.update(query_params["exclude"].split(","))
    if query_params.get("exclude_none") == "true":
        exclude_none = True

    response_model = ResponseModel(
        model=model,
        include=include,
        exclude=exclude,
        exclude_none=exclude_none,
        exclude_unset=exclude_unset,
        exclude_defaults=exclude_defaults,
        by_alias=by_alias,
    )

    return response_model.transform(data)


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
        # Check pagination config and query override
        pagination_config = collection.get_pagination_config()
        query_pagination = params.pop("pagination", "auto")
        if query_pagination == "false":
            include_pagination = False
        elif query_pagination == "true":
            include_pagination = True
        else:
            if pagination_config == "auto":
                include_pagination = None  # Use has_more logic
            else:
                include_pagination = pagination_config

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
        transformed_items = _transform_response(items, collection, request)

        # Build response
        response_data: dict = {"items": transformed_items}

        # Determine if pagination should be included
        should_include_pagination = include_pagination is True or (
            include_pagination is None and (offset + limit < total or offset > 0)
        )

        if should_include_pagination:
            has_more = offset + limit < total
            next_offset = offset + limit if has_more else None
            prev_offset = max(0, offset - limit) if offset > 0 else None
            page = (offset // limit) + 1
            total_pages = max(1, (total + limit - 1) // limit) if limit > 0 else 1

            base_url = str(request.url).split("?")[0] if request.url else ""
            query_params = dict(request.query_params)
            query_params.pop("limit", None)
            query_params.pop("offset", None)
            params_str = "&" + "&".join(f"{k}={v}" for k, v in query_params.items()) if query_params else ""

            response_data["pagination"] = {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": next_offset,
                "prev_offset": prev_offset,
                "page": page,
                "total_pages": total_pages,
            }

            response_data["links"] = {
                "self": f"{base_url}?offset={offset}&limit={limit}{params_str}" if params_str else f"{base_url}?offset={offset}&limit={limit}",
                "next": f"{base_url}?offset={next_offset}&limit={limit}{params_str}" if next_offset is not None and params_str else f"{base_url}?offset={next_offset}&limit={limit}" if next_offset is not None else None,
                "prev": f"{base_url}?offset={prev_offset}&limit={limit}{params_str}" if prev_offset is not None and params_str else f"{base_url}?offset={prev_offset}&limit={limit}" if prev_offset is not None else None,
                "first": f"{base_url}?offset=0&limit={limit}{params_str}" if params_str else f"{base_url}?offset=0&limit={limit}",
                "last": f"{base_url}?offset={(total_pages - 1) * limit}&limit={limit}{params_str}" if params_str else f"{base_url}?offset={(total_pages - 1) * limit}&limit={limit}",
            }

        return JSONResponse(response_data)

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
        transformed = _transform_response(record, collection, request)
        return JSONResponse(transformed)

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
        transformed = _transform_response(record, collection, request)
        return JSONResponse(transformed, status_code=201)

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
        transformed = _transform_response(record, collection, request)
        return JSONResponse(transformed)

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
