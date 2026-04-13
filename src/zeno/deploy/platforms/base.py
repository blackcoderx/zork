"""Abstract base class for platform deployment generators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from cinder.deploy.introspect import AppProfile


@dataclass
class GeneratedFile:
    """A file to be written by a platform generator."""

    path: str  # Relative to output_dir
    content: str


class PlatformGenerator(ABC):
    """Base class for all platform generators."""

    name: str = ""

    def __init__(self, profile: AppProfile, output_dir: Path) -> None:
        self.profile = profile
        self.output_dir = output_dir

    @abstractmethod
    def generate(self) -> list[GeneratedFile]:
        """Return a list of files to create for this platform."""

    def _start_command(self, *, use_port_env: bool = False) -> str:
        port = "$PORT" if use_port_env else str(self.profile.port)
        module_app = f"{self.profile.app_module}:{self.profile.app_variable}"
        return (
            f"gunicorn -k uvicorn.workers.UvicornWorker "
            f"{module_app} --bind 0.0.0.0:{port}"
        )

    def _migrate_command(self) -> str:
        return f"cinderapi migrate run --app {self.profile.app_module}.py"

    def _start_with_migrate(self, *, use_port_env: bool = False) -> str:
        return f"{self._migrate_command()} && {self._start_command(use_port_env=use_port_env)}"

    def _env_vars(self) -> dict[str, str]:
        """Common environment variables for all platforms."""
        env: dict[str, str] = {}
        if self.profile.needs_auth:
            env["CINDER_SECRET"] = "${CINDER_SECRET}"
        return env
