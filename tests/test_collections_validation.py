"""Tests for collection query validation."""

import pytest
from zork.collections.validation import (
    validate_column_name,
    validate_pagination_params,
)
from zork.collections.schema import Collection, TextField, IntField
from zork.errors import ZorkError


@pytest.fixture
def sample_collection():
    return Collection("test", fields=[
        TextField("title"),
        IntField("count"),
    ])


class TestValidateColumnName:
    def test_valid_field_name(self, sample_collection):
        assert validate_column_name("title", sample_collection) == "title"

    def test_valid_int_field(self, sample_collection):
        assert validate_column_name("count", sample_collection) == "count"

    def test_valid_auto_column_id(self, sample_collection):
        assert validate_column_name("id", sample_collection) == "id"

    def test_valid_auto_column_created_at(self, sample_collection):
        assert validate_column_name("created_at", sample_collection) == "created_at"

    def test_valid_auto_column_updated_at(self, sample_collection):
        assert validate_column_name("updated_at", sample_collection) == "updated_at"

    def test_invalid_field_raises_error(self, sample_collection):
        with pytest.raises(ZorkError) as exc:
            validate_column_name("invalid", sample_collection)
        assert exc.value.status_code == 400
        assert "Invalid field" in exc.value.message

    def test_invalid_field_name_in_message(self, sample_collection):
        with pytest.raises(ZorkError) as exc:
            validate_column_name("sql_injection", sample_collection)
        assert "sql_injection" in exc.value.message

    def test_with_extra_columns_config(self, sample_collection):
        config = {"extra_columns": {"custom_field"}}
        result = validate_column_name("custom_field", sample_collection, config)
        assert result == "custom_field"

    def test_extra_columns_config_allows_valid(self, sample_collection):
        config = {"extra_columns": {"extra"}}
        result = validate_column_name("title", sample_collection, config)
        assert result == "title"


class TestValidatePaginationParams:
    def test_default_values(self):
        limit, offset = validate_pagination_params("20", "0")
        assert limit == 20
        assert offset == 0

    def test_custom_values(self):
        limit, offset = validate_pagination_params("10", "50")
        assert limit == 10
        assert offset == 50

    def test_limit_clamped_to_max(self):
        limit, offset = validate_pagination_params("200", "0", {"max_limit": 100})
        assert limit == 100

    def test_limit_clamped_to_max_with_config(self):
        limit, offset = validate_pagination_params(
            "500", "0", {"max_limit": 200, "default_limit": 20}
        )
        assert limit == 200

    def test_negative_limit_becomes_min(self):
        limit, offset = validate_pagination_params("-5", "0")
        assert limit == 1

    def test_zero_limit_becomes_min(self):
        limit, offset = validate_pagination_params("0", "0")
        assert limit == 1

    def test_offset_clamped_to_max(self):
        limit, offset = validate_pagination_params(
            "20", "20000", {"max_offset": 10000}
        )
        assert offset == 10000

    def test_negative_offset_becomes_zero(self):
        limit, offset = validate_pagination_params("20", "-10")
        assert offset == 0

    def test_invalid_limit_defaults_to_default(self):
        limit, offset = validate_pagination_params("abc", "0")
        assert limit == 20

    def test_invalid_offset_defaults_to_zero(self):
        limit, offset = validate_pagination_params("20", "xyz")
        assert offset == 0

    def test_none_limit_uses_default(self):
        limit, offset = validate_pagination_params(None, "0")
        assert limit == 20

    def test_none_offset_defaults_to_zero(self):
        limit, offset = validate_pagination_params("20", None)
        assert offset == 0

    def test_empty_string_limit_uses_default(self):
        limit, offset = validate_pagination_params("", "0")
        assert limit == 20

    def test_custom_default_limit(self):
        limit, offset = validate_pagination_params(
            "", "0", {"default_limit": 50, "max_limit": 100}
        )
        assert limit == 50

    def test_custom_max_offset(self):
        limit, offset = validate_pagination_params(
            "10", "5000", {"max_offset": 3000}
        )
        assert offset == 3000


class TestValidateIntegrationWithCollection:
    def test_field_with_special_chars_in_name(self):
        """Test that fields with underscores are allowed."""
        c = Collection("test", fields=[TextField("created_at")])
        result = validate_column_name("created_at", c)
        assert result == "created_at"

    def test_order_by_with_indexed_field(self):
        """Test that indexed fields work correctly."""
        c = Collection("test", fields=[
            TextField("slug", indexed=True)
        ])
        result = validate_column_name("slug", c)
        assert result == "slug"