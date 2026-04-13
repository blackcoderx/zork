"""Docker deployment generator — Dockerfile, docker-compose.yml, .dockerignore."""

from __future__ import annotations

from textwrap import dedent

from cinder.deploy.introspect import AppProfile
from cinder.deploy.platforms.base import GeneratedFile, PlatformGenerator


class DockerGenerator(PlatformGenerator):
    name = "docker"

    def generate(self) -> list[GeneratedFile]:
        files = [
            GeneratedFile("Dockerfile", self._dockerfile()),
            GeneratedFile(".dockerignore", self._dockerignore()),
            GeneratedFile("docker-compose.yml", self._compose()),
        ]
        return files

    def _dockerfile(self) -> str:
        p = self.profile
        extras = ""
        if p.optional_groups:
            extras = f"[{','.join(p.optional_groups)}]"

        return dedent(f"""\
            # --- Build stage ---
            FROM python:{p.python_version}-slim AS builder

            COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

            WORKDIR /app

            # Install dependencies first for better layer caching
            COPY pyproject.toml uv.lock* ./
            RUN uv sync --frozen --no-dev

            COPY . .

            # --- Runtime stage ---
            FROM python:{p.python_version}-slim

            RUN groupadd -r cinder && useradd -r -g cinder -u 1001 cinder

            WORKDIR /app
            COPY --from=builder /app /app

            # Make sure the virtual env is on PATH
            ENV PATH="/app/.venv/bin:$PATH"
            ENV PYTHONUNBUFFERED=1

            USER cinder
            EXPOSE {p.port}

            # Run migrations then start the server
            CMD ["sh", "-c", "{self._start_with_migrate()}"]
        """)

    def _dockerignore(self) -> str:
        return dedent("""\
            .venv/
            __pycache__/
            *.pyc
            *.pyo
            .git/
            .gitignore
            .env
            .env.*
            *.db
            *.sqlite3
            node_modules/
            web/
            tests/
            .pytest_cache/
            .mypy_cache/
            .ruff_cache/
        """)

    def _compose(self) -> str:
        p = self.profile
        services = self._app_service()

        if p.needs_postgres:
            services += self._postgres_service()
        if p.needs_redis:
            services += self._redis_service()

        volumes = self._volumes()

        return f"services:\n{services}\n{volumes}"

    def _app_service(self) -> str:
        p = self.profile
        env_lines = self._compose_env_lines()
        depends = self._compose_depends()

        return dedent(f"""\
          {p.project_name}:
            build: .
            ports:
              - "{p.port}:{p.port}"
            environment:
              - CINDER_SECRET=${{CINDER_SECRET:-changeme}}
        {env_lines}{depends}    restart: unless-stopped
        """)

    def _compose_env_lines(self) -> str:
        p = self.profile
        lines = ""
        if p.needs_postgres:
            lines += "      - DATABASE_URL=postgresql://cinder:cinder@postgres:5432/cinder\n"
        if p.needs_redis:
            lines += "      - CINDER_REDIS_URL=redis://redis:6379/0\n"
        return lines

    def _compose_depends(self) -> str:
        p = self.profile
        deps: list[str] = []
        if p.needs_postgres:
            deps.append("postgres")
        if p.needs_redis:
            deps.append("redis")
        if not deps:
            return ""
        items = "".join(f"\n          {d}:\n            condition: service_healthy" for d in deps)
        return f"    depends_on:{items}\n"

    def _postgres_service(self) -> str:
        return dedent("""\

          postgres:
            image: postgres:16-alpine
            environment:
              - POSTGRES_USER=cinder
              - POSTGRES_PASSWORD=cinder
              - POSTGRES_DB=cinder
            volumes:
              - pgdata:/var/lib/postgresql/data
            healthcheck:
              test: ["CMD-SHELL", "pg_isready -U cinder"]
              interval: 5s
              timeout: 3s
              retries: 5
        """)

    def _redis_service(self) -> str:
        return dedent("""\

          redis:
            image: redis:7-alpine
            healthcheck:
              test: ["CMD", "redis-cli", "ping"]
              interval: 5s
              timeout: 3s
              retries: 5
        """)

    def _volumes(self) -> str:
        p = self.profile
        entries: list[str] = []
        if p.needs_postgres:
            entries.append("  pgdata:")
        if not entries:
            return ""
        return "volumes:\n" + "\n".join(entries) + "\n"
