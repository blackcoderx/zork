import pytest
from zeno.collections.schema import (
    Collection,
    TextField,
    IntField,
    FloatField,
    BoolField,
    DateTimeField,
    URLField,
    JSONField,
    FileField,
    RelationField,
)


class TestSchemaIndexes:
    def test_field_indexed_default_false(self):
        field = TextField("x")
        assert field.indexed is False

    def test_field_indexed_true(self):
        field = TextField("x", indexed=True)
        assert field.indexed is True

    def test_unique_field_no_index_sql(self):
        collection = Collection("posts", fields=[TextField("slug", unique=True)])
        sqls = collection.build_index_sqls()
        assert sqls == []

    def test_single_field_index_sql(self):
        collection = Collection("posts", fields=[TextField("category", indexed=True)])
        sqls = collection.build_index_sqls()
        assert len(sqls) == 1
        assert (
            "CREATE INDEX IF NOT EXISTS idx_posts_category ON posts (category)"
            in sqls[0]
        )

    def test_composite_index_sql(self):
        collection = Collection(
            "posts",
            fields=[
                TextField("category"),
                TextField("title"),
            ],
            indexes=[("category", "title")],
        )
        sqls = collection.build_index_sqls()
        assert len(sqls) == 1
        assert (
            "CREATE INDEX IF NOT EXISTS idx_posts_category_title ON posts (category, title)"
            in sqls[0]
        )

    def test_index_name_convention_single(self):
        collection = Collection("posts", fields=[TextField("category", indexed=True)])
        sqls = collection.build_index_sqls()
        assert "idx_posts_category" in sqls[0]

    def test_index_name_convention_composite(self):
        collection = Collection(
            "posts",
            fields=[
                TextField("category"),
                TextField("created_at"),
            ],
            indexes=[("category", "created_at")],
        )
        sqls = collection.build_index_sqls()
        assert "idx_posts_category_created_at" in sqls[0]

    def test_collection_no_indexes_empty_list(self):
        collection = Collection(
            "posts",
            fields=[
                TextField("title"),
                TextField("body"),
            ],
        )
        sqls = collection.build_index_sqls()
        assert sqls == []

    def test_multiple_indexed_fields(self):
        collection = Collection(
            "posts",
            fields=[
                TextField("category", indexed=True),
                TextField("status", indexed=True),
            ],
        )
        sqls = collection.build_index_sqls()
        assert len(sqls) == 2

    def test_indexed_unique_field_no_duplicate_index(self):
        collection = Collection(
            "posts", fields=[TextField("slug", unique=True, indexed=True)]
        )
        sqls = collection.build_index_sqls()
        assert sqls == []

    def test_field_indexed_all_types(self):
        fields = [
            TextField("t", indexed=True),
            IntField("i", indexed=True),
            FloatField("f", indexed=True),
            BoolField("b", indexed=True),
            DateTimeField("d", indexed=True),
            URLField("u", indexed=True),
            JSONField("j", indexed=True),
            FileField("file", indexed=True),
            RelationField("rel", collection="users", indexed=True),
        ]
        for f in fields:
            assert f.indexed is True

    def test_collection_indexes_parameter(self):
        collection = Collection(
            "posts",
            fields=[TextField("title")],
            indexes=[("title",), ("title", "created_at")],
        )
        assert len(collection.indexes) == 2
        assert collection.indexes[0] == ("title",)
        assert collection.indexes[1] == ("title", "created_at")
