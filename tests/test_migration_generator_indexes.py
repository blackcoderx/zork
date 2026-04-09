import pytest
from cinder.migrations.diff import AddIndex, DropIndex
from cinder.migrations.generator import generate_migration_content


class TestMigrationGeneratorIndexes:
    def test_add_index_op(self):
        op = AddIndex(
            table="posts", index_name="idx_posts_category", columns=("category",)
        )
        content = generate_migration_content([op], name="test")

        assert (
            "CREATE INDEX IF NOT EXISTS idx_posts_category ON posts (category)"
            in content
        )
        assert "DROP INDEX IF EXISTS idx_posts_category" in content

    def test_add_index_composite(self):
        op = AddIndex(
            table="posts",
            index_name="idx_posts_title_category",
            columns=("title", "category"),
        )
        content = generate_migration_content([op], name="test")

        assert (
            "CREATE INDEX IF NOT EXISTS idx_posts_title_category ON posts (title, category)"
            in content
        )

    def test_drop_index_op(self):
        op = DropIndex(table="posts", index_name="idx_posts_title")
        content = generate_migration_content([op], name="test")

        assert "DESTRUCTIVE" in content
        assert "DROP INDEX IF EXISTS idx_posts_title" in content

    def test_mixed_operations_with_indexes(self):
        from cinder.migrations.diff import AddColumn

        ops = [
            AddColumn(table="posts", field_name="category", col_sql="category TEXT"),
            AddIndex(
                table="posts", index_name="idx_posts_category", columns=("category",)
            ),
        ]
        content = generate_migration_content(ops, name="test")

        assert "ALTER TABLE posts ADD COLUMN category TEXT" in content
        assert (
            "CREATE INDEX IF NOT EXISTS idx_posts_category ON posts (category)"
            in content
        )
