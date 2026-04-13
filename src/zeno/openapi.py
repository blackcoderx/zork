from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from cinder.collections.schema import (
    BoolField,
    Collection,
    DateTimeField,
    Field,
    FileField,
    FloatField,
    IntField,
    JSONField,
    RelationField,
    TextField,
    URLField,
)


SWAGGER_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui.css"/>
    <style>
        html {{ padding: 0; margin: 0; }}
        body {{ margin: 0; padding: 0; }}
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-bundle.js"></script>
    <script>
        window.onload = function() {{
            window.ui = SwaggerUIBundle({{
                url: "/openapi.json",
                dom_id: "#swagger-ui",
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                ],
                docExpansion: "list",
                filter: true,
            }});
        }};
    </script>
</body>
</html>
"""


class CinderOpenAPI:
    def __init__(
        self,
        title: str = "Cinder API",
        version: str = "1.0.0",
        collections: dict[str, tuple[Collection, dict[str, str]]] | None = None,
        auth_enabled: bool = False,
    ) -> None:
        self.title = title
        self.version = version
        self.collections = collections or {}
        self.auth_enabled = auth_enabled

    def to_openapi_dict(self) -> dict[str, Any]:
        return {
            "openapi": "3.1.0",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": "Auto-generated API documentation",
            },
            "paths": self._build_paths(),
            "components": self._build_components(),
        }

    def _build_paths(self) -> dict[str, Any]:
        paths: dict[str, Any] = {}

        paths["/api/health"] = {
            "get": {
                "tags": ["Health"],
                "summary": "Health check",
                "operationId": "health_check",
                "responses": {
                    "200": {
                        "description": "Service is healthy",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/HealthResponse"
                                }
                            }
                        },
                    }
                },
            }
        }

        if self.auth_enabled:
            paths.update(self._build_auth_paths())

        paths.update(self._build_collection_paths())

        return paths

    def _build_auth_paths(self) -> dict[str, Any]:
        paths = {}

        paths["/api/auth/register"] = {
            "post": {
                "tags": ["Authentication"],
                "summary": "Register a new user",
                "operationId": "auth_register",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/RegisterRequest"}
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "User registered successfully",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/AuthResponse"}
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                },
            }
        }

        paths["/api/auth/login"] = {
            "post": {
                "tags": ["Authentication"],
                "summary": "Login with email and password",
                "operationId": "auth_login",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/LoginRequest"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Login successful",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/AuthResponse"}
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                },
            }
        }

        paths["/api/auth/logout"] = {
            "post": {
                "tags": ["Authentication"],
                "summary": "Logout and revoke token",
                "operationId": "auth_logout",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "Logged out successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/MessageResponse"
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                },
            }
        }

        paths["/api/auth/me"] = {
            "get": {
                "tags": ["Authentication"],
                "summary": "Get current authenticated user",
                "operationId": "auth_me",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "Current user data",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/UserResponse"}
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                },
            }
        }

        paths["/api/auth/refresh"] = {
            "post": {
                "tags": ["Authentication"],
                "summary": "Refresh access token",
                "operationId": "auth_refresh",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "New token issued",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/RefreshResponse"
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                },
            }
        }

        paths["/api/auth/forgot-password"] = {
            "post": {
                "tags": ["Authentication"],
                "summary": "Request password reset",
                "operationId": "auth_forgot_password",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/ForgotPasswordRequest"
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Reset email sent if account exists",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/MessageResponse"
                                }
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                },
            }
        }

        paths["/api/auth/verify-email"] = {
            "get": {
                "tags": ["Authentication"],
                "summary": "Verify email address",
                "operationId": "auth_verify_email",
                "parameters": [
                    {
                        "name": "token",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Email verified successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/MessageResponse"
                                }
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                },
            }
        }

        paths["/api/auth/reset-password"] = {
            "post": {
                "tags": ["Authentication"],
                "summary": "Reset password with token",
                "operationId": "auth_reset_password",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/ResetPasswordRequest"
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Password updated successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/MessageResponse"
                                }
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                },
            }
        }

        return paths

    def _build_collection_paths(self) -> dict[str, Any]:
        paths = {}

        for name, (collection, auth_rules) in self.collections.items():
            read_rule = auth_rules.get("read", "public")
            write_rule = auth_rules.get("write", "public")
            tag = name.capitalize()

            list_params = [
                {
                    "name": "limit",
                    "in": "query",
                    "schema": {"type": "integer", "default": 20},
                    "description": "Maximum number of items to return",
                },
                {
                    "name": "offset",
                    "in": "query",
                    "schema": {"type": "integer", "default": 0},
                    "description": "Number of items to skip",
                },
                {
                    "name": "order_by",
                    "in": "query",
                    "schema": {"type": "string", "default": "created_at"},
                    "description": "Field to order by",
                },
                {
                    "name": "expand",
                    "in": "query",
                    "schema": {"type": "string"},
                    "description": "Comma-separated relation fields to expand",
                },
            ]

            list_op = {
                "tags": [tag],
                "summary": f"List {name}",
                "operationId": f"list_{name}",
                "parameters": list_params,
                "responses": {
                    "200": {
                        "description": "List of items",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": f"#/components/schemas/{collection.name.title()}ListResponse"
                                }
                            }
                        },
                    }
                },
            }
            if read_rule != "public":
                list_op["security"] = [{"BearerAuth": []}]

            get_op = {
                "tags": [tag],
                "summary": f"Get {name} by ID",
                "operationId": f"get_{name}",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "expand",
                        "in": "query",
                        "schema": {"type": "string"},
                        "description": "Comma-separated relation fields to expand",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Item details",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": f"#/components/schemas/{collection.name.title()}Response"
                                }
                            }
                        },
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
            if read_rule != "public":
                get_op["security"] = [{"BearerAuth": []}]

            create_op = {
                "tags": [tag],
                "summary": f"Create {name}",
                "operationId": f"create_{name}",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": f"#/components/schemas/{collection.name.title()}CreateRequest"
                            }
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Item created",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": f"#/components/schemas/{collection.name.title()}Response"
                                }
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                },
            }
            if write_rule != "public":
                create_op["security"] = [{"BearerAuth": []}]

            update_op = {
                "tags": [tag],
                "summary": f"Update {name}",
                "operationId": f"update_{name}",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": f"#/components/schemas/{collection.name.title()}UpdateRequest"
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Item updated",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": f"#/components/schemas/{collection.name.title()}Response"
                                }
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
            if write_rule != "public":
                update_op["security"] = [{"BearerAuth": []}]

            delete_op = {
                "tags": [tag],
                "summary": f"Delete {name}",
                "operationId": f"delete_{name}",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Item deleted",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/MessageResponse"
                                }
                            }
                        },
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
            if write_rule != "public":
                delete_op["security"] = [{"BearerAuth": []}]

            base_path = f"/api/{name}"
            paths[base_path] = {
                "get": list_op,
                "post": create_op,
            }
            paths[f"{base_path}/{{id}}"] = {
                "get": get_op,
                "patch": update_op,
                "delete": delete_op,
            }

            for field in collection.fields:
                if isinstance(field, FileField):
                    file_path = f"{base_path}/{{id}}/files/{field.name}"
                    file_tag = f"{tag} Files"

                    paths[file_path] = {
                        "post": {
                            "tags": [file_tag],
                            "summary": f"Upload file to {field.name}",
                            "operationId": f"upload_{name}_{field.name}",
                            "parameters": [
                                {
                                    "name": "id",
                                    "in": "path",
                                    "required": True,
                                    "schema": {"type": "string"},
                                }
                            ],
                            "requestBody": {
                                "required": True,
                                "content": {
                                    "multipart/form-data": {
                                        "schema": {
                                            "$ref": f"#/components/schemas/{collection.name.title()}_{field.name}_UploadRequest"
                                        }
                                    }
                                },
                            },
                            "responses": {
                                "200": {
                                    "description": "File uploaded",
                                    "content": {
                                        "application/json": {
                                            "schema": {
                                                "$ref": f"#/components/schemas/{collection.name.title()}_{field.name}_FileResponse"
                                            }
                                        }
                                    },
                                }
                            },
                        },
                        "get": {
                            "tags": [file_tag],
                            "summary": f"Download file from {field.name}",
                            "operationId": f"download_{name}_{field.name}",
                            "parameters": [
                                {
                                    "name": "id",
                                    "in": "path",
                                    "required": True,
                                    "schema": {"type": "string"},
                                }
                            ],
                            "responses": {
                                "200": {
                                    "description": "File content",
                                    "content": {
                                        "application/octet-stream": {
                                            "schema": {
                                                "type": "string",
                                                "format": "binary",
                                            }
                                        }
                                    },
                                }
                            },
                        },
                        "delete": {
                            "tags": [file_tag],
                            "summary": f"Delete file from {field.name}",
                            "operationId": f"delete_{name}_{field.name}",
                            "parameters": [
                                {
                                    "name": "id",
                                    "in": "path",
                                    "required": True,
                                    "schema": {"type": "string"},
                                }
                            ],
                            "responses": {
                                "200": {
                                    "description": "File deleted",
                                    "content": {
                                        "application/json": {
                                            "schema": {
                                                "$ref": "#/components/schemas/MessageResponse"
                                            }
                                        }
                                    },
                                }
                            },
                        },
                    }

        return paths

    def _build_components(self) -> dict[str, Any]:
        schemas: dict[str, Any] = {
            "HealthResponse": {
                "type": "object",
                "properties": {"status": {"type": "string", "example": "ok"}},
            },
            "MessageResponse": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
            },
            "RegisterRequest": {
                "type": "object",
                "required": ["email", "password"],
                "properties": {
                    "email": {"type": "string", "format": "email"},
                    "password": {
                        "type": "string",
                        "format": "password",
                        "minLength": 8,
                    },
                    "username": {"type": "string"},
                },
            },
            "LoginRequest": {
                "type": "object",
                "required": ["email", "password"],
                "properties": {
                    "email": {"type": "string", "format": "email"},
                    "password": {"type": "string", "format": "password"},
                },
            },
            "AuthResponse": {
                "type": "object",
                "properties": {
                    "token": {"type": "string"},
                    "user": {"$ref": "#/components/schemas/UserResponse"},
                },
            },
            "UserResponse": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "email": {"type": "string"},
                    "username": {"type": "string"},
                    "role": {"type": "string"},
                    "is_verified": {"type": "boolean"},
                    "is_active": {"type": "boolean"},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"},
                },
            },
            "RefreshResponse": {
                "type": "object",
                "properties": {"token": {"type": "string"}},
            },
            "ForgotPasswordRequest": {
                "type": "object",
                "required": ["email"],
                "properties": {"email": {"type": "string", "format": "email"}},
            },
            "ResetPasswordRequest": {
                "type": "object",
                "required": ["token", "new_password"],
                "properties": {
                    "token": {"type": "string"},
                    "new_password": {
                        "type": "string",
                        "format": "password",
                        "minLength": 8,
                    },
                },
            },
            "BadRequest": {
                "description": "Bad Request",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"error": {"type": "string"}},
                        }
                    }
                },
            },
            "Unauthorized": {
                "description": "Unauthorized",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"error": {"type": "string"}},
                        }
                    }
                },
            },
            "Forbidden": {
                "description": "Forbidden",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"error": {"type": "string"}},
                        }
                    }
                },
            },
            "NotFound": {
                "description": "Not Found",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"error": {"type": "string"}},
                        }
                    }
                },
            },
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT token obtained from login",
            },
        }

        for name, (collection, _) in self.collections.items():
            title_name = name.title()
            schemas[f"{title_name}Response"] = self._collection_to_response_schema(
                collection
            )
            schemas[f"{title_name}ListResponse"] = {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"$ref": f"#/components/schemas/{title_name}Response"},
                    },
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
            }

            create_fields = {}
            update_fields = {}
            for field in collection.fields:
                if isinstance(field, FileField):
                    continue
                json_schema = self._field_to_json_schema(field)
                if field.required:
                    create_fields[field.name] = {"type": "object", **json_schema}
                else:
                    create_fields[field.name] = {
                        "type": "object",
                        **json_schema,
                        "default": field.default,
                    }
                update_fields[field.name] = {
                    "type": "object",
                    **json_schema,
                    "nullable": True,
                }

            schemas[f"{title_name}CreateRequest"] = {
                "type": "object",
                "properties": create_fields,
            }
            schemas[f"{title_name}UpdateRequest"] = {
                "type": "object",
                "properties": update_fields,
            }

            for field in collection.fields:
                if isinstance(field, FileField):
                    field_name = field.name.title()
                    schemas[f"{title_name}_{field.name}_UploadRequest"] = {
                        "type": "object",
                        "properties": {
                            "file": {
                                "type": "string",
                                "format": "binary",
                                "description": "The file to upload",
                            }
                        },
                    }
                    schemas[f"{title_name}_{field.name}_FileResponse"] = {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "key": {"type": "string"},
                            "name": {"type": "string"},
                            "size": {"type": "integer"},
                            "mime": {"type": "string"},
                        },
                    }

        return {
            "schemas": schemas,
            "securitySchemes": {"BearerAuth": schemas.pop("BearerAuth")},
            "responses": {
                "BadRequest": schemas.pop("BadRequest"),
                "Unauthorized": schemas.pop("Unauthorized"),
                "Forbidden": schemas.pop("Forbidden"),
                "NotFound": schemas.pop("NotFound"),
            },
        }

    def _field_to_json_schema(self, field: Field) -> dict[str, Any]:
        schema: dict[str, Any] = {}

        if isinstance(field, TextField):
            schema["type"] = "string"
            if field.min_length is not None:
                schema["minLength"] = field.min_length
            if field.max_length is not None:
                schema["maxLength"] = field.max_length
        elif isinstance(field, IntField):
            schema["type"] = "integer"
            if field.min_value is not None:
                schema["minimum"] = field.min_value
            if field.max_value is not None:
                schema["maximum"] = field.max_value
        elif isinstance(field, FloatField):
            schema["type"] = "number"
            if field.min_value is not None:
                schema["minimum"] = field.min_value
            if field.max_value is not None:
                schema["maximum"] = field.max_value
        elif isinstance(field, BoolField):
            schema["type"] = "boolean"
        elif isinstance(field, DateTimeField):
            schema["type"] = "string"
            schema["format"] = "date-time"
        elif isinstance(field, URLField):
            schema["type"] = "string"
            schema["format"] = "uri"
        elif isinstance(field, JSONField):
            schema["type"] = "object"
        elif isinstance(field, RelationField):
            schema["type"] = "string"
            schema["description"] = f"ID of related {field.collection} record"
        elif isinstance(field, FileField):
            schema["type"] = "object"
        else:
            schema["type"] = "string"

        return schema

    def _collection_to_response_schema(self, collection: Collection) -> dict[str, Any]:
        properties = {
            "id": {"type": "string"},
            "created_at": {"type": "string"},
            "updated_at": {"type": "string"},
        }

        for field in collection.fields:
            properties[field.name] = self._field_to_json_schema(field)

        return {"type": "object", "properties": properties}

    async def _get_openapi_json(self, request: Request) -> JSONResponse:
        return JSONResponse(self.to_openapi_dict())

    async def _get_docs(self, request: Request) -> HTMLResponse:
        return HTMLResponse(SWAGGER_HTML.format(title=json.dumps(self.title)[1:-1]))

    def build_routes(self) -> list[Route]:
        return [
            Route("/openapi.json", self._get_openapi_json, methods=["GET"]),
            Route("/docs", self._get_docs, methods=["GET"]),
        ]
