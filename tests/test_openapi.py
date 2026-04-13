import pytest
from starlette.testclient import TestClient

from zeno.app import Zeno
from zeno.collections.schema import (
    BoolField,
    Collection,
    DateTimeField,
    FileField,
    FloatField,
    IntField,
    TextField,
)
from zeno.auth import Auth
from zeno.openapi import ZenoOpenAPI
from zeno.storage.backends import LocalFileBackend


@pytest.fixture
def app(db_path):
    zeno = Zeno(
        database=db_path,
        title="Test API",
        version="2.0.0",
    )

    posts = Collection(
        "posts",
        fields=[
            TextField("title", required=True, min_length=1, max_length=200),
            TextField("slug"),
            IntField("views", default=0, min_value=0),
            FloatField("rating", min_value=0.0, max_value=5.0),
            BoolField("published", default=False),
            DateTimeField("published_at"),
        ],
    )
    zeno.register(posts, auth=["read:public", "write:public"])
    return zeno


@pytest.fixture
def app_with_file_field(db_path, tmp_path):
    zeno = Zeno(
        database=db_path,
        title="Test API with Files",
        version="2.0.0",
    )

    posts = Collection(
        "posts",
        fields=[
            TextField("title", required=True),
            FileField("cover"),
        ],
    )
    zeno.configure_storage(LocalFileBackend(str(tmp_path / "uploads")))
    zeno.register(posts, auth=["read:public", "write:public"])
    return zeno


@pytest.fixture
def app_with_auth(db_path):
    zeno = Zeno(
        database=db_path,
        title="Auth API",
        version="1.0.0",
    )

    posts = Collection(
        "posts",
        fields=[
            TextField("title", required=True),
        ],
    )
    auth = Auth(token_expiry=3600, allow_registration=True)

    zeno.register(posts, auth=["read:authenticated", "write:authenticated"])
    zeno.use_auth(auth)
    return zeno


@pytest.fixture
def app_no_auth(db_path):
    zeno = Zeno(database=db_path)
    posts = Collection("posts", fields=[TextField("title", required=True)])
    zeno.register(posts, auth=["read:public", "write:public"])
    return zeno


class TestZenoOpenAPI:
    def test_openapi_endpoint_returns_json(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"

    def test_openapi_schema_is_valid(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        assert data["openapi"] == "3.1.0"
        assert data["info"]["title"] == "Test API"
        assert data["info"]["version"] == "2.0.0"
        assert "paths" in data
        assert "components" in data

    def test_docs_endpoint_returns_html(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.get("/docs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "swagger-ui" in resp.text.lower()

    def test_health_endpoint_in_schema(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        assert "/api/health" in data["paths"]
        assert "get" in data["paths"]["/api/health"]

    def test_collection_paths_generated(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        assert "/api/posts" in data["paths"]
        assert "/api/posts/{id}" in data["paths"]

    def test_crud_operations_generated(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        post_paths = data["paths"]["/api/posts"]
        assert "get" in post_paths
        assert "post" in post_paths

        post_id_paths = data["paths"]["/api/posts/{id}"]
        assert "get" in post_id_paths
        assert "patch" in post_id_paths
        assert "delete" in post_id_paths

    def test_file_field_routes_generated(self, app_with_file_field):
        starlette_app = app_with_file_field.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        file_path = "/api/posts/{id}/files/cover"
        assert file_path in data["paths"]
        assert "post" in data["paths"][file_path]
        assert "get" in data["paths"][file_path]
        assert "delete" in data["paths"][file_path]

    def test_auth_paths_not_in_public_app(self, app_no_auth):
        starlette_app = app_no_auth.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        assert "/api/auth/login" not in data["paths"]
        assert "/api/auth/register" not in data["paths"]

    def test_auth_paths_in_authenticated_app(self, app_with_auth):
        starlette_app = app_with_auth.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        assert "/api/auth/login" in data["paths"]
        assert "/api/auth/register" in data["paths"]
        assert "/api/auth/logout" in data["paths"]
        assert "/api/auth/me" in data["paths"]
        assert "/api/auth/refresh" in data["paths"]
        assert "/api/auth/forgot-password" in data["paths"]
        assert "/api/auth/verify-email" in data["paths"]
        assert "/api/auth/reset-password" in data["paths"]

    def test_auth_endpoints_require_bearer_auth(self, app_with_auth):
        starlette_app = app_with_auth.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        assert "security" in data["paths"]["/api/auth/logout"]["post"]
        assert "security" in data["paths"]["/api/auth/me"]["get"]
        assert "security" in data["paths"]["/api/auth/refresh"]["post"]

    def test_public_endpoints_no_auth_required(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        assert "/api/posts" in data["paths"]
        list_op = data["paths"]["/api/posts"]["get"]
        assert "security" not in list_op

    def test_authenticated_endpoints_require_auth(self, app_with_auth):
        starlette_app = app_with_auth.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        list_op = data["paths"]["/api/posts"]["get"]
        assert "security" in list_op

    def test_query_parameters_documented(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        list_params = data["paths"]["/api/posts"]["get"]["parameters"]
        param_names = [p["name"] for p in list_params]
        assert "limit" in param_names
        assert "offset" in param_names
        assert "order_by" in param_names
        assert "expand" in param_names

    def test_path_id_parameter_documented(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        get_params = data["paths"]["/api/posts/{id}"]["get"]["parameters"]
        param_names = [p["name"] for p in get_params]
        assert "id" in param_names

    def test_field_types_in_schema(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        schemas = data["components"]["schemas"]
        assert "PostsResponse" in schemas
        assert "PostsCreateRequest" in schemas
        assert "PostsUpdateRequest" in schemas

    def test_default_title_and_version(self, db_path):
        zeno = Zeno(database=db_path)
        posts = Collection("posts", fields=[TextField("title")])
        zeno.register(posts)

        starlette_app = zeno.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        assert data["info"]["title"] == "Zeno API"
        assert data["info"]["version"] == "1.0.0"

    def test_schema_with_int_constraints(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        schemas = data["components"]["schemas"]
        views_field = schemas["PostsCreateRequest"]["properties"]["views"]
        assert views_field.get("type") == "integer"
        assert "minimum" in views_field

    def test_schema_with_string_constraints(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        schemas = data["components"]["schemas"]
        title_field = schemas["PostsCreateRequest"]["properties"]["title"]
        assert title_field.get("type") == "string"
        assert "minLength" in title_field
        assert "maxLength" in title_field

    def test_list_response_schema(self, app):
        starlette_app = app.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        schemas = data["components"]["schemas"]
        assert "PostsListResponse" in schemas
        list_schema = schemas["PostsListResponse"]
        assert "items" in list_schema["properties"]
        assert "total" in list_schema["properties"]
        assert "limit" in list_schema["properties"]
        assert "offset" in list_schema["properties"]


class TestZenoOpenAPIStandalone:
    def test_standalone_openapi_generator(self):
        posts = Collection(
            "posts",
            fields=[
                TextField("title", required=True),
                IntField("count", default=0),
            ],
        )

        collections = {"posts": (posts, {"read": "public", "write": "public"})}

        openapi = ZenoOpenAPI(
            title="My API",
            version="3.0.0",
            collections=collections,
            auth_enabled=True,
        )

        schema = openapi.to_openapi_dict()

        assert schema["info"]["title"] == "My API"
        assert schema["info"]["version"] == "3.0.0"
        assert "/api/posts" in schema["paths"]
        assert "/api/auth/login" in schema["paths"]

    def test_openapi_without_auth(self):
        posts = Collection("posts", fields=[TextField("title")])
        collections = {"posts": (posts, {"read": "public", "write": "public"})}

        openapi = ZenoOpenAPI(
            title="Public API",
            version="1.0.0",
            collections=collections,
            auth_enabled=False,
        )

        schema = openapi.to_openapi_dict()

        assert "/api/auth/login" not in schema["paths"]
        assert "/api/auth/register" not in schema["paths"]

    def test_security_scheme_bearer_auth(self, app_with_auth):
        starlette_app = app_with_auth.build()
        client = TestClient(starlette_app)

        resp = client.get("/openapi.json")
        data = resp.json()

        assert "BearerAuth" in data["components"]["securitySchemes"]
        bearer_scheme = data["components"]["securitySchemes"]["BearerAuth"]
        assert bearer_scheme["type"] == "http"
        assert bearer_scheme["scheme"] == "bearer"
