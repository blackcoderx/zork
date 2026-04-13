"""Fly.io deployment generator — fly.toml + Dockerfile."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from cinder.deploy.platforms.base import GeneratedFile, PlatformGenerator
from cinder.deploy.platforms.docker import DockerGenerator


class FlyGenerator(PlatformGenerator):
    name = "fly"

    def generate(self) -> list[GeneratedFile]:
        files = [GeneratedFile("fly.toml", self._fly_toml())]

        # Reuse Docker generator for the Dockerfile
        docker = DockerGenerator(self.profile, self.output_dir)
        files.append(GeneratedFile("Dockerfile", docker._dockerfile()))
        files.append(GeneratedFile(".dockerignore", docker._dockerignore()))

        return files

    def _fly_toml(self) -> str:
        p = self.profile
        return dedent(f"""\
            app = "{p.project_name}"
            primary_region = "iad"

            [build]

            [deploy]
              release_command = "{self._migrate_command()}"

            [http_service]
              internal_port = {p.port}
              force_https = true
              auto_stop_machines = "stop"
              auto_start_machines = true
              min_machines_running = 1

              [http_service.concurrency]
                type = "connections"
                hard_limit = 250
                soft_limit = 200

            [[http_service.checks]]
              grace_period = "10s"
              interval = "15s"
              method = "GET"
              path = "/api/health"
              timeout = "2s"

            [[vm]]
              memory = "512mb"
              cpu_kind = "shared"
              cpus = 1
        """)

    def post_generate_instructions(self) -> str:
        p = self.profile
        lines = [
            "Fly.io setup instructions:",
            "",
            "1. Install the Fly CLI: https://fly.io/docs/flyctl/install/",
            "2. Run: fly launch --no-deploy  (to create the app)",
            "3. Set secrets:",
            "   fly secrets set CINDER_SECRET=$(cinderapi generate-secret)",
        ]
        if p.needs_postgres:
            lines += [
                "",
                "4. Create a Postgres cluster:",
                "   fly postgres create --name {}-db".format(p.project_name),
                "   fly postgres attach {}-db".format(p.project_name),
            ]
        if p.needs_redis:
            lines += [
                "",
                "{}. Set up Redis (via Upstash):".format(
                    "5" if p.needs_postgres else "4"
                ),
                "   fly redis create",
                "   fly secrets set CINDER_REDIS_URL=<redis-url-from-above>",
            ]
        lines += ["", "Deploy: fly deploy"]
        return "\n".join(lines)
