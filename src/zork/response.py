from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel


class ResponseModel:
    """Wrapper for transforming and serializing API responses.

    Provides fine-grained control over which fields are included/excluded
    from responses, supports field aliases, computed properties, and
    various serialization options.

    Usage with collections::

        from pydantic import BaseModel

        class UserResponse(BaseModel):
            id: str
            name: str
            email: str

        users.response(
            model=UserResponse,
            exclude={"password_hash"}
        )

    Usage with decorator::

        @app.response(UserResponse, include={"id", "name"})
        async def get_user(request):
            return await fetch_user(request.path_params["id"])

    Args:
        model: Pydantic BaseModel class for validation and transformation
        include: Set of field names to include in response
        exclude: Set of field names to exclude from response
        exclude_none: Whether to exclude fields with None values
        exclude_unset: Whether to exclude fields not explicitly set
        exclude_defaults: Whether to exclude fields with default values
        by_alias: Whether to use field aliases in output
        transform: Optional custom transform function (record) -> record

    Example::

        from pydantic import BaseModel
        from zork.response import ResponseModel

        class ArticleResponse(BaseModel):
            id: str
            title: str
            slug: str  # computed
            is_published: bool

            @model_validator(mode="before")
            def compute_slug(cls, data):
                if isinstance(data, dict) and "title" in data:
                    data["slug"] = data["title"].lower().replace(" ", "-")
                return data

        response_model = ResponseModel(
            model=ArticleResponse,
            include={"id", "title", "slug"},
            exclude_none=True
        )

        result = response_model.transform({"id": "1", "title": "Hello World"})
        # {"id": "1", "title": "Hello World", "slug": "hello-world"}
    """

    def __init__(
        self,
        model: type[BaseModel] | None = None,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
        exclude_none: bool = False,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        by_alias: bool = False,
        transform: Callable[[dict], dict] | None = None,
    ):
        self.model = model
        self.include = include
        self.exclude = exclude or set()
        self.exclude_none = exclude_none
        self.exclude_unset = exclude_unset
        self.exclude_defaults = exclude_defaults
        self.by_alias = by_alias
        self.transform_fn = transform

    def _build_exclude_set(self, data: dict) -> set[str]:
        """Build the effective exclude set from all sources."""
        exclude = set(self.exclude)

        if self.model is not None:
            exclude.update(self._get_hidden_fields())

        return exclude

    def _get_hidden_fields(self) -> set[str]:
        """Extract hidden fields from model config or field metadata."""
        hidden = set()
        if self.model is not None:
            config = getattr(self.model, "model_config", {})
            if isinstance(config, dict):
                hidden_fields = config.get("hidden_fields", [])
                hidden.update(hidden_fields)
        return hidden

    def transform(self, data: Any) -> Any:
        """Transform data through the response model.

        Args:
            data: Single record (dict) or list of records

        Returns:
            Transformed data with fields included/excluded according to config

        Example::

            response_model = ResponseModel(
                include={"id", "name"},
                exclude={"internal_id"}
            )

            single = response_model.transform({"id": "1", "name": "John", "internal_id": "X"})
            # {"id": "1", "name": "John"}

            multiple = response_model.transform([
                {"id": "1", "name": "John"},
                {"id": "2", "name": "Jane"}
            ])
            # [{"id": "1", "name": "John"}, {"id": "2", "name": "Jane"}]
        """
        if data is None:
            return None

        if isinstance(data, list):
            return [self.transform(item) for item in data]

        if not isinstance(data, dict):
            return data

        if self.model is not None:
            try:
                instance = self.model(**data)
                return instance.model_dump(
                    include=self.include,
                    exclude=self._build_exclude_set(data),
                    exclude_none=self.exclude_none,
                    exclude_unset=self.exclude_unset,
                    exclude_defaults=self.exclude_defaults,
                    by_alias=self.by_alias,
                )
            except Exception:
                pass

        exclude = self._build_exclude_set(data)

        result = {}
        for key, value in data.items():
            if key in exclude:
                continue
            if self.include is not None and key not in self.include:
                continue
            if self.exclude_none and value is None:
                continue
            result[key] = value

        if self.transform_fn is not None:
            result = self.transform_fn(result)

        return result


def create_response_model(
    model: type[BaseModel] | None = None,
    include: set[str] | None = None,
    exclude: set[str] | None = None,
    exclude_none: bool = False,
    exclude_unset: bool = False,
    exclude_defaults: bool = False,
    by_alias: bool = False,
    hidden_fields: list[str] | None = None,
) -> ResponseModel:
    """Factory function to create a ResponseModel with hidden fields support.

    Args:
        model: Pydantic BaseModel class
        include: Fields to include
        exclude: Fields to exclude
        exclude_none: Exclude None values
        exclude_unset: Exclude unset values
        exclude_defaults: Exclude default values
        by_alias: Use field aliases
        hidden_fields: List of field names to always exclude

    Returns:
        Configured ResponseModel instance

    Example::

        from pydantic import BaseModel
        from zork.response import create_response_model

        class User(BaseModel):
            id: str
            name: str
            email: str
            password: str

        UserPublicResponse = create_response_model(
            model=User,
            exclude={"password"},
            exclude_none=True
        )
    """
    if hidden_fields and model is not None:
        from pydantic import ConfigDict
        model_config_dict = dict(getattr(model, "model_config", {}))
        model_config_dict["hidden_fields"] = list(model_config_dict.get("hidden_fields", [])) + hidden_fields

        hidden = hidden_fields

        class ConfiguredModel(model):
            model_config = ConfigDict(**model_config_dict)

        model = ConfiguredModel

    return ResponseModel(
        model=model,
        include=include,
        exclude=exclude,
        exclude_none=exclude_none,
        exclude_unset=exclude_unset,
        exclude_defaults=exclude_defaults,
        by_alias=by_alias,
    )