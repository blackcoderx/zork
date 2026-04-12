"""Inspect a Cinder app instance to build a deployment profile."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

from cinder.cache.backends import RedisCacheBackend
from cinder.ratelimit.backends import RedisRateLimitBackend


@dataclass
class AppProfile:
    """Everything the deployment generators need to know about the app."""

    app_module: str
    app_variable: str
    project_name: str
    python_version: str
    port: int = 8000

    # Database
    needs_postgres: bool = False
    needs_mysql: bool = False
    needs_sqlite: bool = False

    # Services
    needs_redis: bool = False
    needs_auth: bool = False
    needs_s3: bool = False
    needs_email: bool = False

    # Detected optional dependencies for the generated requirements
    optional_groups: list[str] = field(default_factory=list)


def introspect(app_path: str) -> AppProfile:
    """Load the Cinder app at *app_path* and return an :class:`AppProfile`."""
    from cinder.app import Cinder

    path = Path(app_path).resolve()
    parent = str(path.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    module_name = path.stem
    module = importlib.import_module(module_name)

    # Find the Cinder instance and its variable name
    cinder_app: Cinder | None = None
    var_name = "app"
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, Cinder):
            cinder_app = attr
            var_name = attr_name
            break

    if cinder_app is None:
        raise RuntimeError(f"No Cinder instance found in {app_path}")

    # --- Detect database type ---
    import os

    db_url = (
        os.getenv("CINDER_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or cinder_app.database
    )
    needs_postgres = db_url.startswith(("postgresql://", "postgres://"))
    needs_mysql = db_url.startswith(("mysql://", "mysql+aiomysql://"))
    needs_sqlite = not needs_postgres and not needs_mysql

    # --- Detect Redis usage ---
    redis_url = os.getenv("CINDER_REDIS_URL")
    needs_redis = bool(redis_url)
    if not needs_redis:
        # Check if cache or rate-limit backends are Redis-backed
        if isinstance(cinder_app.cache._backend, RedisCacheBackend):
            needs_redis = True
        elif isinstance(cinder_app.rate_limit._backend, RedisRateLimitBackend):
            needs_redis = True

    # --- Auth, S3, Email ---
    needs_auth = cinder_app._auth is not None
    needs_s3 = cinder_app._storage_backend is not None
    needs_email = cinder_app.email._backend is not None

    # --- Python version ---
    python_version = _detect_python_version(path.parent)

    # --- Project name ---
    project_name = _detect_project_name(path.parent)

    # --- Optional dependency groups ---
    groups: list[str] = []
    if needs_postgres:
        groups.append("postgres")
    if needs_mysql:
        groups.append("mysql")
    if needs_redis:
        groups.append("redis")
    if needs_s3:
        groups.append("s3")
    if needs_email:
        groups.append("email")

    return AppProfile(
        app_module=module_name,
        app_variable=var_name,
        project_name=project_name,
        python_version=python_version,
        needs_postgres=needs_postgres,
        needs_mysql=needs_mysql,
        needs_sqlite=needs_sqlite,
        needs_redis=needs_redis,
        needs_auth=needs_auth,
        needs_s3=needs_s3,
        needs_email=needs_email,
        optional_groups=groups,
    )


def _detect_python_version(project_dir: Path) -> str:
    """Read requires-python from pyproject.toml, or fall back to current runtime."""
    import re

    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8")
        m = re.search(r'requires-python\s*=\s*"([^"]+)"', text)
        if m:
            spec = m.group(1)  # e.g. ">=3.10"
            digits = re.search(r"(\d+\.\d+)", spec)
            if digits:
                return digits.group(1)
    # Fallback
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _detect_project_name(project_dir: Path) -> str:
    """Read project name from pyproject.toml, or fall back to directory name."""
    import re

    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8")
        m = re.search(r'name\s*=\s*"([^"]+)"', text)
        if m:
            return m.group(1)
    return project_dir.name
