from __future__ import annotations

from collections import defaultdict
from typing import Callable

from cinder.collections.schema import Field


class Auth:
    def __init__(
        self,
        *,
        token_expiry: int = 86400,
        allow_registration: bool = True,
        extend_user: list[Field] | None = None,
    ):
        self.token_expiry = token_expiry
        self.allow_registration = allow_registration
        self.extend_user = extend_user or []
        self._hooks: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, handler: Callable) -> None:
        self._hooks[event].append(handler)

    def get_extend_columns_sql(self) -> list[str]:
        return [f.column_sql() for f in self.extend_user]
