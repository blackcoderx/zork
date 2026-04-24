"""Input validation utilities for collection queries."""

from zork.errors import ZorkError

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_OFFSET = 10000


def validate_column_name(name: str, collection, config: dict | None = None) -> str:
    """Validate that a column name exists in the collection schema.

    Args:
        name: The column/field name to validate
        collection: Collection instance with fields
        config: Optional config dict with custom allowed names

    Returns:
        The validated column name

    Raises:
        ZorkError: If column name is invalid
    """
    allowed = {f.name for f in collection.fields}
    allowed.update({"id", "created_at", "updated_at"})

    if config and "extra_columns" in config:
        allowed.update(config["extra_columns"])

    if name not in allowed:
        raise ZorkError(400, f"Invalid field: {name}")
    return name


def validate_pagination_params(
    limit: str | int,
    offset: str | int,
    config: dict | None = None,
) -> tuple[int, int]:
    """Validate and normalize pagination parameters.

    Args:
        limit: Raw limit value (from query params or int)
        offset: Raw offset value (from query params or int)
        config: Optional config with max_limit, default_limit, max_offset

    Returns:
        Tuple of (validated_limit, validated_offset)

    Raises:
        ZorkError: If values are invalid
    """
    defaults = {
        "max_limit": MAX_LIMIT,
        "default_limit": DEFAULT_LIMIT,
        "max_offset": MAX_OFFSET,
    }
    if config:
        defaults.update(config)

    max_limit = defaults["max_limit"]
    default_limit = defaults["default_limit"]
    max_offset = defaults["max_offset"]

    try:
        limit_val = int(limit) if limit else default_limit
    except (ValueError, TypeError):
        limit_val = default_limit

    limit_val = max(1, min(limit_val, max_limit))

    try:
        offset_val = int(offset) if offset else 0
    except (ValueError, TypeError):
        offset_val = 0

    offset_val = max(0, min(offset_val, max_offset))

    return limit_val, offset_val
