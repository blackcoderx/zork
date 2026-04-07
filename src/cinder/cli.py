from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import typer

app = typer.Typer(
    name="cinder", help="Cinder — A lightweight backend framework for Python."
)


@app.command()
def serve(
    app_path: str = typer.Argument(
        ..., help="Path to the Python file containing the Cinder app"
    ),
    reload: bool = typer.Option(
        False, "--reload", help="Enable auto-reload for development"
    ),
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", help="Port to bind to"),
):
    """Start the Cinder application server."""
    import uvicorn

    path = Path(app_path).resolve()
    if not path.exists():
        typer.echo(f"Error: File not found: {app_path}", err=True)
        raise typer.Exit(1)

    sys.path.insert(0, str(path.parent))
    module_name = path.stem

    module = importlib.import_module(module_name)

    from cinder.app import Cinder

    cinder_app = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, Cinder):
            cinder_app = attr
            break

    if cinder_app is None:
        typer.echo("Error: No Cinder instance found in the module", err=True)
        raise typer.Exit(1)

    starlette_app = cinder_app.build()
    uvicorn.run(starlette_app, host=host, port=port, reload=reload)


@app.command()
def init(
    project_name: str = typer.Argument(..., help="Name of the project to create"),
):
    """Scaffold a new Cinder project."""
    project_path = Path(project_name)
    project_path.mkdir(parents=True, exist_ok=True)

    main_content = """from cinder import Cinder, Collection, TextField, IntField, Auth

app = Cinder(database="app.db")

posts = Collection("posts", fields=[
    TextField("title", required=True),
    TextField("body"),
    IntField("views", default=0),
])

auth = Auth(token_expiry=86400, allow_registration=True)

app.register(posts, auth=["read:public", "write:authenticated"])
app.use_auth(auth)

if __name__ == "__main__":
    app.serve()
"""
    (project_path / "main.py").write_text(main_content)

    env_content = "# CINDER_SECRET=your-secret-key-here\n"
    (project_path / ".env").write_text(env_content)

    gitignore_content = "*.db\n.env\n__pycache__/\n.venv/\n"
    (project_path / ".gitignore").write_text(gitignore_content)

    typer.echo(f"Project created at {project_path.resolve()}")
    typer.echo(f"  cd {project_name}")
    typer.echo(f"  cinder serve main.py")


@app.command()
def promote(
    email: str = typer.Argument(..., help="Email of the user to promote"),
    role: str = typer.Option("admin", "--role", help="Role to assign"),
    database: str = typer.Option(
        "app.db", "--database", help="Path to the database file"
    ),
):
    """Promote a user to a new role."""
    from cinder.db.connection import Database

    async def _promote():
        db = Database(database)
        await db.connect()
        try:
            user = await db.fetch_one(
                "SELECT id, email, role FROM _users WHERE email = ?", (email,)
            )
            if user is None:
                typer.echo(f"Error: User with email '{email}' not found", err=True)
                raise typer.Exit(1)

            await db.execute(
                "UPDATE _users SET role = ? WHERE email = ?", (role, email)
            )
            typer.echo(f"User '{email}' promoted to role '{role}'")
        finally:
            await db.disconnect()

    asyncio.run(_promote())
