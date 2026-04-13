"""Platform-specific deployment generators."""

from cinder.deploy.platforms.docker import DockerGenerator
from cinder.deploy.platforms.fly import FlyGenerator
from cinder.deploy.platforms.railway import RailwayGenerator
from cinder.deploy.platforms.render import RenderGenerator

PLATFORMS: dict[str, type] = {
    "docker": DockerGenerator,
    "railway": RailwayGenerator,
    "render": RenderGenerator,
    "fly": FlyGenerator,
}

__all__ = [
    "PLATFORMS",
    "DockerGenerator",
    "RailwayGenerator",
    "RenderGenerator",
    "FlyGenerator",
]
