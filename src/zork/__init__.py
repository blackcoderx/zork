"""Zork — A lightweight backend framework for Python.

A lightweight, open-source backend framework for Python. Define your data schema
— Zork auto-generates a full REST API with auth, CRUD, filtering, and more.
"""

from dotenv import load_dotenv

from zork.app import Zork
from zork.auth import Auth
from zork.cache.backends import CacheBackend, MemoryCacheBackend, RedisCacheBackend
from zork.collections.schema import (
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
from zork.db.connection import Database
from zork.errors import ZorkError
from zork.ratelimit.backends import (
    MemoryRateLimitBackend,
    RateLimitBackend,
    RedisRateLimitBackend,
)
from zork.ratelimit.middleware import RateLimitRule
from zork.response import ResponseModel
from zork.logging import configure_from_env, get_logger, setup
from zork.staticfiles import StaticFilesConfig

load_dotenv()


__all__ = [
    "Zork",
    "Auth",
    "Collection",
    "Field",
    "TextField",
    "IntField",
    "FloatField",
    "BoolField",
    "DateTimeField",
    "URLField",
    "JSONField",
    "RelationField",
    "FileField",
    "ZorkError",
    # Database
    "Database",
    # Cache
    "CacheBackend",
    "MemoryCacheBackend",
    "RedisCacheBackend",
    # Rate limit
    "RateLimitBackend",
    "MemoryRateLimitBackend",
    "RedisRateLimitBackend",
    "RateLimitRule",
    # Response
    "ResponseModel",
    # Logging
    "setup",
    "configure_from_env",
    "get_logger",
    # Static files
    "StaticFilesConfig",
]
