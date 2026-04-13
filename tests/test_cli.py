import pytest
import asyncio
from typer.testing import CliRunner
from zeno.cli import app

runner = CliRunner()


class TestInit:
    def test_init_creates_project(self, tmp_path):
        result = runner.invoke(app, ["init", str(tmp_path / "myproject")])
        assert result.exit_code == 0
        project_dir = tmp_path / "myproject"
        assert project_dir.exists()
        assert (project_dir / "main.py").exists()
        assert (project_dir / ".env").exists()
        assert (project_dir / ".gitignore").exists()

    def test_init_main_py_content(self, tmp_path):
        runner.invoke(app, ["init", str(tmp_path / "myproject")])
        content = (tmp_path / "myproject" / "main.py").read_text()
        assert "from zeno" in content
        assert "Zeno" in content


class TestPromote:
    def test_promote_user(self, db_path):
        from zeno.db.connection import Database
        from zeno.auth.models import create_auth_tables

        async def setup():
            db = Database(db_path)
            await db.connect()
            await create_auth_tables(db)
            await db.execute(
                "INSERT INTO _users (id, email, password, role, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("u1", "admin@test.com", "hashed", "user", "2026-01-01", "2026-01-01"),
            )
            await db.disconnect()

        asyncio.run(setup())

        result = runner.invoke(app, [
            "promote", "admin@test.com", "--role", "admin", "--database", db_path
        ])
        assert result.exit_code == 0
        assert "admin" in result.stdout.lower()
