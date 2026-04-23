"""Tests for the zork deploy command and deployment generators."""

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zork.cli import app
from zork.deploy.config import generate_zork_toml
from zork.deploy.introspect import AppProfile
from zork.deploy.platforms.base import GeneratedFile
from zork.deploy.platforms.docker import DockerGenerator
from zork.deploy.platforms.fly import FlyGenerator
from zork.deploy.platforms.railway import RailwayGenerator
from zork.deploy.platforms.render import RenderGenerator

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def basic_profile():
    return AppProfile(
        app_module="main",
        app_variable="app",
        project_name="myapp",
        python_version="3.12",
        needs_postgres=True,
        needs_redis=True,
        needs_auth=True,
    )


@pytest.fixture
def sqlite_profile():
    return AppProfile(
        app_module="main",
        app_variable="app",
        project_name="myapp",
        python_version="3.12",
        needs_sqlite=True,
    )


@pytest.fixture
def sample_app(tmp_path):
    """Create a minimal Zork app file for CLI tests."""
    app_file = tmp_path / "main.py"
    app_file.write_text(
        'from zork import Zork\napp = Zork(database="app.db", title="Test")\n'
    )
    return app_file


# ---------------------------------------------------------------------------
# Docker Generator
# ---------------------------------------------------------------------------


class TestDockerGenerator:
    def test_generates_three_files(self, basic_profile, tmp_path):
        gen = DockerGenerator(basic_profile, tmp_path)
        files = gen.generate()
        names = [f.path for f in files]
        assert "Dockerfile" in names
        assert ".dockerignore" in names
        assert "docker-compose.yml" in names

    def test_dockerfile_uses_correct_python(self, basic_profile, tmp_path):
        gen = DockerGenerator(basic_profile, tmp_path)
        files = {f.path: f.content for f in gen.generate()}
        assert "python:3.12-slim" in files["Dockerfile"]

    def test_dockerfile_has_nonroot_user(self, basic_profile, tmp_path):
        gen = DockerGenerator(basic_profile, tmp_path)
        files = {f.path: f.content for f in gen.generate()}
        assert "useradd" in files["Dockerfile"]
        assert "USER zork" in files["Dockerfile"]

    def test_dockerfile_has_uv(self, basic_profile, tmp_path):
        gen = DockerGenerator(basic_profile, tmp_path)
        files = {f.path: f.content for f in gen.generate()}
        assert "ghcr.io/astral-sh/uv" in files["Dockerfile"]

    def test_compose_has_postgres_when_needed(self, basic_profile, tmp_path):
        gen = DockerGenerator(basic_profile, tmp_path)
        files = {f.path: f.content for f in gen.generate()}
        assert "postgres:" in files["docker-compose.yml"]
        assert "pgdata:" in files["docker-compose.yml"]

    def test_compose_has_redis_when_needed(self, basic_profile, tmp_path):
        gen = DockerGenerator(basic_profile, tmp_path)
        files = {f.path: f.content for f in gen.generate()}
        assert "redis:" in files["docker-compose.yml"]

    def test_compose_no_postgres_for_sqlite(self, sqlite_profile, tmp_path):
        gen = DockerGenerator(sqlite_profile, tmp_path)
        files = {f.path: f.content for f in gen.generate()}
        assert "postgres:" not in files["docker-compose.yml"]

    def test_dockerignore_excludes_venv(self, basic_profile, tmp_path):
        gen = DockerGenerator(basic_profile, tmp_path)
        files = {f.path: f.content for f in gen.generate()}
        assert ".venv/" in files[".dockerignore"]

    def test_dockerfile_has_migrate(self, basic_profile, tmp_path):
        gen = DockerGenerator(basic_profile, tmp_path)
        files = {f.path: f.content for f in gen.generate()}
        assert "zork migrate run" in files["Dockerfile"]


# ---------------------------------------------------------------------------
# Railway Generator
# ---------------------------------------------------------------------------


class TestRailwayGenerator:
    def test_generates_railway_toml(self, basic_profile, tmp_path):
        gen = RailwayGenerator(basic_profile, tmp_path)
        files = gen.generate()
        assert len(files) == 1
        assert files[0].path == "railway.toml"

    def test_has_health_check(self, basic_profile, tmp_path):
        gen = RailwayGenerator(basic_profile, tmp_path)
        content = gen.generate()[0].content
        assert "/api/health" in content

    def test_has_nixpacks_builder(self, basic_profile, tmp_path):
        gen = RailwayGenerator(basic_profile, tmp_path)
        content = gen.generate()[0].content
        assert "NIXPACKS" in content

    def test_start_command_uses_port_env(self, basic_profile, tmp_path):
        gen = RailwayGenerator(basic_profile, tmp_path)
        content = gen.generate()[0].content
        assert "$PORT" in content

    def test_start_command_includes_migrate(self, basic_profile, tmp_path):
        gen = RailwayGenerator(basic_profile, tmp_path)
        content = gen.generate()[0].content
        assert "zork migrate run" in content

    def test_post_instructions_mention_postgres(self, basic_profile, tmp_path):
        gen = RailwayGenerator(basic_profile, tmp_path)
        instructions = gen.post_generate_instructions()
        assert "PostgreSQL" in instructions

    def test_post_instructions_mention_redis(self, basic_profile, tmp_path):
        gen = RailwayGenerator(basic_profile, tmp_path)
        instructions = gen.post_generate_instructions()
        assert "Redis" in instructions


# ---------------------------------------------------------------------------
# Render Generator
# ---------------------------------------------------------------------------


class TestRenderGenerator:
    def test_generates_render_yaml(self, basic_profile, tmp_path):
        gen = RenderGenerator(basic_profile, tmp_path)
        files = gen.generate()
        assert len(files) == 1
        assert files[0].path == "render.yaml"

    def test_has_health_check(self, basic_profile, tmp_path):
        gen = RenderGenerator(basic_profile, tmp_path)
        content = gen.generate()[0].content
        assert "/api/health" in content

    def test_has_generate_value_for_secret(self, basic_profile, tmp_path):
        gen = RenderGenerator(basic_profile, tmp_path)
        content = gen.generate()[0].content
        assert "generateValue: true" in content

    def test_has_database_section_for_postgres(self, basic_profile, tmp_path):
        gen = RenderGenerator(basic_profile, tmp_path)
        content = gen.generate()[0].content
        assert "databases:" in content
        assert "fromDatabase:" in content

    def test_has_redis_section(self, basic_profile, tmp_path):
        gen = RenderGenerator(basic_profile, tmp_path)
        content = gen.generate()[0].content
        assert "keyvalues:" in content

    def test_no_database_for_sqlite(self, sqlite_profile, tmp_path):
        gen = RenderGenerator(sqlite_profile, tmp_path)
        content = gen.generate()[0].content
        assert "databases:" not in content


# ---------------------------------------------------------------------------
# Fly.io Generator
# ---------------------------------------------------------------------------


class TestFlyGenerator:
    def test_generates_three_files(self, basic_profile, tmp_path):
        gen = FlyGenerator(basic_profile, tmp_path)
        files = gen.generate()
        names = [f.path for f in files]
        assert "fly.toml" in names
        assert "Dockerfile" in names
        assert ".dockerignore" in names

    def test_fly_toml_has_health_check(self, basic_profile, tmp_path):
        gen = FlyGenerator(basic_profile, tmp_path)
        files = {f.path: f.content for f in gen.generate()}
        assert "/api/health" in files["fly.toml"]

    def test_fly_toml_has_release_command(self, basic_profile, tmp_path):
        gen = FlyGenerator(basic_profile, tmp_path)
        files = {f.path: f.content for f in gen.generate()}
        assert "release_command" in files["fly.toml"]
        assert "zork migrate run" in files["fly.toml"]

    def test_fly_toml_force_https(self, basic_profile, tmp_path):
        gen = FlyGenerator(basic_profile, tmp_path)
        files = {f.path: f.content for f in gen.generate()}
        assert "force_https = true" in files["fly.toml"]

    def test_post_instructions_mention_secrets(self, basic_profile, tmp_path):
        gen = FlyGenerator(basic_profile, tmp_path)
        instructions = gen.post_generate_instructions()
        assert "fly secrets set" in instructions

    def test_post_instructions_mention_postgres(self, basic_profile, tmp_path):
        gen = FlyGenerator(basic_profile, tmp_path)
        instructions = gen.post_generate_instructions()
        assert "fly postgres create" in instructions


# ---------------------------------------------------------------------------
# zork.toml Config
# ---------------------------------------------------------------------------


class TestZorkToml:
    def test_generates_valid_toml(self, basic_profile):
        content = generate_zork_toml(basic_profile, "railway")
        assert "[project]" in content
        assert 'name = "myapp"' in content
        assert 'platform = "railway"' in content

    def test_database_type_postgresql(self, basic_profile):
        content = generate_zork_toml(basic_profile, "docker")
        assert 'database = "postgresql"' in content

    def test_database_type_sqlite(self, sqlite_profile):
        content = generate_zork_toml(sqlite_profile, "docker")
        assert 'database = "sqlite"' in content

    def test_redis_true(self, basic_profile):
        content = generate_zork_toml(basic_profile, "docker")
        assert "redis = true" in content

    def test_redis_false(self, sqlite_profile):
        content = generate_zork_toml(sqlite_profile, "docker")
        assert "redis = false" in content


# ---------------------------------------------------------------------------
# Platform Auto-Detection
# ---------------------------------------------------------------------------


class TestPlatformDetection:
    def test_detect_railway(self, monkeypatch):
        from zork.cli import _detect_platform

        monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
        assert _detect_platform() == "railway"

    def test_detect_render(self, monkeypatch):
        from zork.cli import _detect_platform

        monkeypatch.setenv("RENDER", "true")
        assert _detect_platform() == "render"

    def test_detect_fly(self, monkeypatch):
        from zork.cli import _detect_platform

        monkeypatch.setenv("FLY_APP_NAME", "myapp")
        assert _detect_platform() == "fly"

    def test_default_docker(self, monkeypatch):
        from zork.cli import _detect_platform

        monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
        monkeypatch.delenv("RENDER", raising=False)
        monkeypatch.delenv("FLY_APP_NAME", raising=False)
        assert _detect_platform() == "docker"


# ---------------------------------------------------------------------------
# CLI Integration (dry-run)
# ---------------------------------------------------------------------------


class TestDeployCLI:
    def test_dry_run_docker(self, sample_app):
        result = runner.invoke(
            app,
            [
                "deploy",
                "--platform",
                "docker",
                "--app",
                str(sample_app),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Dockerfile" in result.stdout
        assert "docker-compose.yml" in result.stdout
        assert "zork.toml" in result.stdout

    def test_dry_run_railway(self, sample_app):
        result = runner.invoke(
            app,
            [
                "deploy",
                "--platform",
                "railway",
                "--app",
                str(sample_app),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "railway.toml" in result.stdout

    def test_dry_run_render(self, sample_app):
        result = runner.invoke(
            app,
            [
                "deploy",
                "--platform",
                "render",
                "--app",
                str(sample_app),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "render.yaml" in result.stdout

    def test_dry_run_fly(self, sample_app):
        result = runner.invoke(
            app,
            [
                "deploy",
                "--platform",
                "fly",
                "--app",
                str(sample_app),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "fly.toml" in result.stdout

    def test_unknown_platform_fails(self, sample_app):
        result = runner.invoke(
            app,
            [
                "deploy",
                "--platform",
                "heroku",
                "--app",
                str(sample_app),
            ],
        )
        assert result.exit_code == 1

    def test_missing_app_file_fails(self):
        result = runner.invoke(
            app,
            [
                "deploy",
                "--platform",
                "docker",
                "--app",
                "nonexistent.py",
            ],
        )
        assert result.exit_code == 1

    def test_sqlite_warning_on_paas(self, sample_app, capsys):
        result = runner.invoke(
            app,
            [
                "deploy",
                "--platform",
                "railway",
                "--app",
                str(sample_app),
                "--dry-run",
            ],
        )
        # SQLite app on railway should produce a warning
        assert "SQLite" in (result.stdout + (result.stderr or ""))

    def test_force_overwrites(self, sample_app):
        output_dir = sample_app.parent
        # Pre-create a file
        (output_dir / "railway.toml").write_text("old content")
        result = runner.invoke(
            app,
            [
                "deploy",
                "--platform",
                "railway",
                "--app",
                str(sample_app),
                "--force",
            ],
        )
        assert result.exit_code == 0
        new_content = (output_dir / "railway.toml").read_text()
        assert "old content" not in new_content
        assert "NIXPACKS" in new_content


# ---------------------------------------------------------------------------
# Introspection Tests
# ---------------------------------------------------------------------------


class TestIntrospect:
    def test_introspect_sqlite_by_default(self, tmp_path, monkeypatch):
        from zork.deploy.introspect import introspect

        app_file = tmp_path / "main.py"
        app_file.write_text(
            'from zork import Zork\napp = Zork(database="app.db", title="Test")\n'
        )
        monkeypatch.delenv("ZORK_DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("ZORK_REDIS_URL", raising=False)

        profile = introspect(str(app_file))

        assert profile.app_module == "main"
        assert profile.app_variable == "app"
        assert profile.needs_sqlite is True
        assert profile.needs_postgres is False
        assert profile.needs_mysql is False
        assert profile.needs_redis is False

    def test_introspect_postgres_via_env(self, tmp_path, monkeypatch):
        from zork.deploy.introspect import introspect

        app_file = tmp_path / "main.py"
        app_file.write_text(
            'from zork import Zork\napp = Zork(database="app.db", title="Test")\n'
        )
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        monkeypatch.delenv("ZORK_REDIS_URL", raising=False)

        profile = introspect(str(app_file))

        assert profile.needs_postgres is True
        assert profile.needs_sqlite is False
        assert "postgres" in profile.optional_groups

    def test_introspect_mysql_via_env(self, tmp_path, monkeypatch):
        from zork.deploy.introspect import introspect

        app_file = tmp_path / "main.py"
        app_file.write_text(
            'from zork import Zork\napp = Zork(database="app.db", title="Test")\n'
        )
        monkeypatch.setenv("DATABASE_URL", "mysql://user:pass@localhost/db")
        monkeypatch.delenv("ZORK_REDIS_URL", raising=False)

        profile = introspect(str(app_file))

        assert profile.needs_mysql is True
        assert profile.needs_sqlite is False

    def test_introspect_redis_via_env(self, tmp_path, monkeypatch):
        from zork.deploy.introspect import introspect

        app_file = tmp_path / "main.py"
        app_file.write_text(
            'from zork import Zork\napp = Zork(database="app.db", title="Test")\n'
        )
        monkeypatch.setenv("ZORK_REDIS_URL", "redis://localhost:6379/0")

        profile = introspect(str(app_file))

        assert profile.needs_redis is True
        assert "redis" in profile.optional_groups

    def test_introspect_project_name_from_pyproject(self, tmp_path, monkeypatch):
        from zork.deploy.introspect import _detect_project_name

        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "my-awesome-project"\n'
        )

        name = _detect_project_name(tmp_path)

        assert name == "my-awesome-project"

    def test_introspect_project_name_fallback(self, tmp_path):
        from zork.deploy.introspect import _detect_project_name

        name = _detect_project_name(tmp_path)

        assert name == tmp_path.name

    def test_introspect_python_version_from_pyproject(self, tmp_path):
        from zork.deploy.introspect import _detect_python_version

        (tmp_path / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.11"\n'
        )

        version = _detect_python_version(tmp_path)

        assert version == "3.11"

    def test_introspect_python_version_fallback(self, tmp_path):
        from zork.deploy.introspect import _detect_python_version

        version = _detect_python_version(tmp_path)

        import sys

        assert version == f"{sys.version_info.major}.{sys.version_info.minor}"
