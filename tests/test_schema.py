import pytest
from datetime import datetime
from zeno.collections.schema import (
    Field, TextField, IntField, FloatField, BoolField,
    DateTimeField, URLField, JSONField, RelationField, Collection,
)


class TestFieldTypes:
    def test_text_field_sqlite_type(self):
        f = TextField("name")
        assert f.sqlite_type() == "TEXT"
        assert f.name == "name"

    def test_text_field_required(self):
        f = TextField("title", required=True)
        assert f.required is True

    def test_text_field_defaults(self):
        f = TextField("bio", default="empty")
        assert f.default == "empty"

    def test_int_field(self):
        f = IntField("age", min_value=0, max_value=150)
        assert f.sqlite_type() == "INTEGER"
        assert f.min_value == 0
        assert f.max_value == 150

    def test_float_field(self):
        f = FloatField("price", required=True)
        assert f.sqlite_type() == "REAL"

    def test_float_field_constraints(self):
        f = FloatField("rating", min_value=0.0, max_value=5.0)
        assert f.min_value == 0.0
        assert f.max_value == 5.0

    def test_bool_field(self):
        f = BoolField("active", default=True)
        assert f.sqlite_type() == "INTEGER"
        assert f.default is True

    def test_datetime_field(self):
        f = DateTimeField("published_at")
        assert f.sqlite_type() == "TEXT"

    def test_datetime_field_auto_now(self):
        f = DateTimeField("updated_at", auto_now=True)
        assert f.auto_now is True

    def test_url_field(self):
        f = URLField("website")
        assert f.sqlite_type() == "TEXT"

    def test_json_field(self):
        f = JSONField("metadata")
        assert f.sqlite_type() == "TEXT"

    def test_relation_field(self):
        f = RelationField("category", collection="categories")
        assert f.sqlite_type() == "TEXT"
        assert f.collection == "categories"

    def test_field_unique(self):
        f = TextField("email", unique=True)
        assert f.unique is True


class TestCollection:
    def test_collection_creation(self):
        c = Collection("posts", fields=[
            TextField("title", required=True),
            TextField("body"),
        ])
        assert c.name == "posts"
        assert len(c.fields) == 2

    def test_collection_hook_registration(self):
        c = Collection("posts", fields=[TextField("title")])
        handler = lambda record, ctx: record
        c.on("before_create", handler)
        assert len(c._registry.get("posts:before_create")) == 1
        assert c._registry.get("posts:before_create")[0] is handler

    def test_build_create_table_sql(self):
        c = Collection("posts", fields=[
            TextField("title", required=True),
            IntField("views", default=0),
            BoolField("published", default=False),
        ])
        sql = c.build_create_table_sql()
        assert "CREATE TABLE IF NOT EXISTS posts" in sql
        assert "id TEXT PRIMARY KEY" in sql
        assert "title TEXT NOT NULL" in sql
        assert "views INTEGER" in sql
        assert "published INTEGER" in sql
        assert "created_at TEXT NOT NULL" in sql
        assert "updated_at TEXT NOT NULL" in sql

    def test_build_create_table_sql_with_unique(self):
        c = Collection("users", fields=[
            TextField("email", required=True, unique=True),
        ])
        sql = c.build_create_table_sql()
        assert "email TEXT NOT NULL UNIQUE" in sql

    def test_build_pydantic_model_validates_required(self):
        c = Collection("posts", fields=[
            TextField("title", required=True),
            TextField("body"),
        ])
        Model = c.build_pydantic_model()
        instance = Model(title="Hello")
        assert instance.title == "Hello"
        assert instance.body is None

    def test_build_pydantic_model_rejects_missing_required(self):
        from pydantic import ValidationError
        c = Collection("posts", fields=[
            TextField("title", required=True),
        ])
        Model = c.build_pydantic_model()
        with pytest.raises(ValidationError):
            Model()

    def test_build_pydantic_model_applies_defaults(self):
        c = Collection("posts", fields=[
            IntField("views", default=0),
        ])
        Model = c.build_pydantic_model()
        instance = Model()
        assert instance.views == 0

    def test_build_pydantic_model_url_validation(self):
        from pydantic import ValidationError
        c = Collection("links", fields=[
            URLField("url", required=True),
        ])
        Model = c.build_pydantic_model()
        instance = Model(url="https://example.com")
        assert "example.com" in str(instance.url)
        with pytest.raises(ValidationError):
            Model(url="not-a-url")

    def test_build_pydantic_model_int_constraints(self):
        from pydantic import ValidationError
        c = Collection("items", fields=[
            IntField("qty", min_value=0, max_value=100),
        ])
        Model = c.build_pydantic_model()
        instance = Model(qty=50)
        assert instance.qty == 50
        with pytest.raises(ValidationError):
            Model(qty=-1)
        with pytest.raises(ValidationError):
            Model(qty=101)

    def test_build_pydantic_model_float_constraints(self):
        from pydantic import ValidationError
        c = Collection("reviews", fields=[
            FloatField("rating", min_value=0.0, max_value=5.0),
        ])
        Model = c.build_pydantic_model()
        instance = Model(rating=4.5)
        assert instance.rating == 4.5
        with pytest.raises(ValidationError):
            Model(rating=-0.1)
        with pytest.raises(ValidationError):
            Model(rating=5.1)

    def test_build_pydantic_model_required_float(self):
        from pydantic import ValidationError
        c = Collection("products", fields=[
            FloatField("price", required=True),
        ])
        Model = c.build_pydantic_model()
        assert Model(price=9.99).price == 9.99
        with pytest.raises(ValidationError):
            Model()  # price is required
