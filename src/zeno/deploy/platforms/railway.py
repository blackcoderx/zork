"""Railway deployment generator — railway.toml."""

from __future__ import annotations

from textwrap import dedent

from cinder.deploy.platforms.base import GeneratedFile, PlatformGenerator


class RailwayGenerator(PlatformGenerator):
    name = "railway"

    def generate(self) -> list[GeneratedFile]:
        return [GeneratedFile("railway.toml", self._railway_toml())]

    def _railway_toml(self) -> str:
        p = self.profile
        return dedent(f"""\
            [build]
            builder = "NIXPACKS"

            [deploy]
            startCommand = "{self._start_with_migrate(use_port_env=True)}"
            healthcheckPath = "/api/health"
            healthcheckTimeout = 5
            restartPolicyType = "ON_FAILURE"
            restartPolicyMaxRetries = 3
        """)

    def post_generate_instructions(self) -> str:
        p = self.profile
        lines = [
            "Railway setup instructions:",
            "",
            "1. Push this repo to GitHub and connect it to a Railway project.",
            "2. Add the following environment variables in Railway dashboard:",
            "   - CINDER_SECRET  (use `cinderapi generate-secret` to create one)",
        ]
        if p.needs_postgres:
            lines += [
                "",
                "3. Add a PostgreSQL service:",
                "   - Click 'New' → 'Database' → 'PostgreSQL'",
                "   - Add a reference variable: DATABASE_URL = ${{Postgres.DATABASE_URL}}",
            ]
        if p.needs_redis:
            lines += [
                "",
                f"{'4' if p.needs_postgres else '3'}. Add a Redis service:",
                "   - Click 'New' → 'Database' → 'Redis'",
                "   - Add a reference variable: CINDER_REDIS_URL = ${{Redis.REDIS_URL}}",
            ]
        return "\n".join(lines)
