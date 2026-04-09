import pytest
from cinder.collections.schema import Collection, TextField
from cinder.migrations.diff import SchemaComparator, AddIndex, DropIndex


class TestMigrationDiffIndexes:
    async def test_diff_add_index(self, mem_db):
        await mem_db.execute(
            "CREATE TABLE posts (id TEXT PRIMARY KEY, title TEXT, category TEXT)"
        )

        collection = Collection(
            "posts",
            fields=[
                TextField("title"),
                TextField("category", indexed=True),
            ],
        )
        comparator = SchemaComparator(mem_db, [collection])
        operations = await comparator.diff()

        add_indexes = [op for op in operations if isinstance(op, AddIndex)]
        assert len(add_indexes) == 1
        assert add_indexes[0].index_name == "idx_posts_category"
        assert add_indexes[0].columns == ("category",)

    async def test_diff_no_index_change(self, mem_db):
        await mem_db.execute(
            "CREATE TABLE posts (id TEXT PRIMARY KEY, title TEXT, category TEXT)"
        )
        await mem_db.execute("CREATE INDEX idx_posts_category ON posts (category)")

        collection = Collection(
            "posts",
            fields=[
                TextField("title"),
                TextField("category", indexed=True),
            ],
        )
        comparator = SchemaComparator(mem_db, [collection])
        operations = await comparator.diff()

        add_indexes = [op for op in operations if isinstance(op, AddIndex)]
        assert add_indexes == []

    async def test_diff_drop_index(self, mem_db):
        await mem_db.execute(
            "CREATE TABLE posts (id TEXT PRIMARY KEY, title TEXT, category TEXT)"
        )
        await mem_db.execute("CREATE INDEX idx_posts_title ON posts (title)")

        collection = Collection(
            "posts",
            fields=[
                TextField("category", indexed=True),
            ],
        )
        comparator = SchemaComparator(mem_db, [collection])
        operations = await comparator.diff()

        drop_indexes = [op for op in operations if isinstance(op, DropIndex)]
        assert len(drop_indexes) == 1
        assert drop_indexes[0].index_name == "idx_posts_title"
        assert drop_indexes[0].destructive is True

    async def test_diff_composite_index_add(self, mem_db):
        await mem_db.execute(
            "CREATE TABLE posts (id TEXT PRIMARY KEY, title TEXT, category TEXT)"
        )

        collection = Collection(
            "posts",
            fields=[
                TextField("title"),
                TextField("category"),
            ],
            indexes=[("title", "category")],
        )
        comparator = SchemaComparator(mem_db, [collection])
        operations = await comparator.diff()

        add_indexes = [op for op in operations if isinstance(op, AddIndex)]
        assert len(add_indexes) == 1
        assert add_indexes[0].index_name == "idx_posts_title_category"
        assert add_indexes[0].columns == ("title", "category")
