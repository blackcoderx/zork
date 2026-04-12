"""Generate cinder.toml deployment configuration."""

from __future__ import annotations

from cinder.deploy.introspect import AppProfile


def generate_cinder_toml(profile: AppProfile, platform: str) -> str:
    """Return the content of a ``cinder.toml`` file."""
    db_type = "postgresql" if profile.needs_postgres else "mysql" if profile.needs_mysql else "sqlite"
    redis_line = "true" if profile.needs_redis else "false"

    return (
        f'[project]\n'
        f'name = "{profile.project_name}"\n'
        f'python_version = "{profile.python_version}"\n'
        f'\n'
        f'[deploy]\n'
        f'platform = "{platform}"\n'
        f'app_path = "{profile.app_module}.py"\n'
        f'port = {profile.port}\n'
        f'workers = 4\n'
        f'\n'
        f'[services]\n'
        f'database = "{db_type}"\n'
        f'redis = {redis_line}\n'
        f'\n'
        f'[health]\n'
        f'path = "/api/health"\n'
        f'interval = 10\n'
        f'timeout = 5\n'
    )
