"""Render deployment generator — render.yaml."""

from __future__ import annotations

from textwrap import dedent

from cinder.deploy.platforms.base import GeneratedFile, PlatformGenerator


class RenderGenerator(PlatformGenerator):
    name = "render"

    def generate(self) -> list[GeneratedFile]:
        return [GeneratedFile("render.yaml", self._render_yaml())]

    def _render_yaml(self) -> str:
        p = self.profile
        sections = [self._web_service()]
        if p.needs_postgres:
            sections.append(self._database())
        if p.needs_redis:
            sections.append(self._redis())
        return "\n".join(sections)

    def _web_service(self) -> str:
        p = self.profile
        env_vars = self._env_var_lines()
        return dedent(f"""\
            services:
              - type: web
                name: {p.project_name}
                runtime: python
                buildCommand: pip install uv && uv sync --frozen --no-dev
                startCommand: {self._start_with_migrate(use_port_env=True)}
                healthCheckPath: /api/health
                envVars:
                  - key: CINDER_SECRET
                    generateValue: true
                  - key: PYTHON_VERSION
                    value: "{p.python_version}"
        {env_vars}""")

    def _env_var_lines(self) -> str:
        p = self.profile
        lines = ""
        if p.needs_postgres:
            lines += dedent("""\
                  - key: DATABASE_URL
                    fromDatabase:
                      name: {name}-db
                      property: connectionString
            """).format(name=p.project_name)
        if p.needs_redis:
            lines += dedent("""\
                  - key: CINDER_REDIS_URL
                    fromService:
                      name: {name}-redis
                      type: keyvalue
                      property: connectionString
            """).format(name=p.project_name)
        return lines

    def _database(self) -> str:
        p = self.profile
        return dedent(f"""\
            databases:
              - name: {p.project_name}-db
                plan: free
        """)

    def _redis(self) -> str:
        p = self.profile
        return dedent(f"""\
            keyvalues:
              - name: {p.project_name}-redis
                plan: free
        """)
