from __future__ import annotations

import asyncio
import importlib
import importlib.metadata
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer(
    name="zeno", help="Zeno — A lightweight backend framework for Python."
)

migrate_app = typer.Typer(help="Manage database schema migrations.")
app.add_typer(migrate_app, name="migrate")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_app(app_path: str):
    """Load a Zeno instance from a Python file.

    Returns ``(zeno_instance, resolved_path)``.
    Raises ``typer.Exit(1)`` with an error message if the file is not found or
    no Zeno instance is present.
    """
    from zeno.app import Zeno

    path = Path(app_path).resolve()
    if not path.exists():
        typer.echo(f"Error: File not found: {app_path}", err=True)
        raise typer.Exit(1)

    parent = str(path.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    module_name = path.stem
    module = importlib.import_module(module_name)

    zeno_instance = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, Zeno):
            zeno_instance = attr
            break

    if zeno_instance is None:
        typer.echo("Error: No Zeno instance found in the module", err=True)
        raise typer.Exit(1)

    return zeno_instance, path


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def serve(
    app_path: str = typer.Argument(
        ..., help="Path to the Python file containing the Zeno app"
    ),
    reload: bool = typer.Option(
        False, "--reload", help="Enable auto-reload for development"
    ),
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", help="Port to bind to"),
):
    """Start the Zeno application server."""
    import uvicorn

    zeno_app, _ = _load_app(app_path)
    starlette_app = zeno_app.build()
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
    typer.echo("cinderapi serve main.py")


@app.command()
def promote(
    email: str = typer.Argument(..., help="Email of the user to promote"),
    role: str = typer.Option("admin", "--role", help="Role to assign"),
    database: str = typer.Option(
        "app.db", "--database", help="Path to the database file"
    ),
):
    """Promote a user to a new role."""
    from zeno.db.connection import Database

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


@app.command("generate-secret")
def generate_secret():
    """Generate a secure random secret key."""
    typer.echo(secrets.token_hex(32))


@app.command()
def doctor(
    app_path: Optional[str] = typer.Option(
        None, "--app", help="Path to the Python file containing the Zeno app"
    ),
    database: Optional[str] = typer.Option(
        None, "--database", help="Database URL to check"
    ),
):
    """Check connectivity to configured services."""
    from zeno.db.connection import Database

    # Resolve the DB URL
    if app_path is not None:
        zeno_app, _ = _load_app(app_path)
        db_url = zeno_app.database
    elif database is not None:
        db_url = database
    else:
        db_url = (
            os.environ.get("CINDER_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or "app.db"
        )

    all_ok = True

    # --- Database check ---
    async def _check_db(url: str) -> tuple[bool, str]:
        db = Database(url)
        try:
            await db.connect()
            await db.fetch_one("SELECT 1")
            return True, url
        except Exception as exc:
            return False, str(exc)
        finally:
            await db.disconnect()

    db_ok, db_detail = asyncio.run(_check_db(db_url))
    if db_ok:
        db_masked = re.sub(r"://([^:@]+):([^@]+)@", "://***:***@", db_url)
        display = db_masked if len(db_masked) <= 40 else db_masked[:40] + "..."
        typer.echo(f"[OK] Database: {display}")
    else:
        typer.echo(f"[FAIL] Database: {db_detail}")
        all_ok = False

    # --- Redis check ---
    redis_url = os.environ.get("CINDER_REDIS_URL") or os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis.asyncio as aioredis

            async def _check_redis(url: str) -> tuple[bool, str]:
                try:
                    client = aioredis.from_url(url)
                    await client.ping()
                    await client.aclose()
                    return True, url
                except Exception as exc:
                    return False, str(exc)

            redis_ok, redis_detail = asyncio.run(_check_redis(redis_url))
            if redis_ok:
                redis_masked = re.sub(r"://([^:@]+):([^@]+)@", "://***:***@", redis_url)
                redis_display = (
                    redis_masked
                    if len(redis_masked) <= 40
                    else redis_masked[:40] + "..."
                )
                typer.echo(f"[OK] Redis: {redis_display}")
            else:
                typer.echo(f"[FAIL] Redis: {redis_detail}")
                all_ok = False
        except ImportError:
            typer.echo("[SKIP] Redis: redis package not installed")

    if not all_ok:
        raise typer.Exit(1)


@app.command()
def routes(
    app_path: str = typer.Option(
        ..., "--app", help="Path to the Python file containing the Zeno app"
    ),
):
    """List all registered routes."""
    from starlette.routing import Mount, Route, WebSocketRoute

    zeno_app, _ = _load_app(app_path)
    built = zeno_app.build()

    # build() returns a LazyInitMiddleware wrapping the middleware stack.
    # Walk inward to find the Starlette app that has .routes.
    from starlette.applications import Starlette

    starlette_app = built
    while starlette_app is not None and not isinstance(starlette_app, Starlette):
        # Middleware wrappers store the inner app in .app or ._inner
        starlette_app = getattr(starlette_app, "app", None) or getattr(
            starlette_app, "_inner", None
        )

    if starlette_app is None or not hasattr(starlette_app, "routes"):
        typer.echo("Error: Could not resolve routes from the built app.", err=True)
        raise typer.Exit(1)

    collected: list[tuple[str, str, str]] = []

    def _walk(route_list, prefix: str = "") -> None:
        for route in route_list:
            if isinstance(route, Mount):
                mount_prefix = prefix + (route.path or "")
                sub_routes = getattr(route, "routes", None) or []
                _walk(sub_routes, mount_prefix)
            elif isinstance(route, (Route, WebSocketRoute)):
                full_path = prefix + route.path
                if isinstance(route, WebSocketRoute):
                    method = "WS"
                else:
                    methods = route.methods
                    method = ",".join(sorted(methods)) if methods else "*"
                name = route.name or ""
                collected.append((method, full_path, name))

    _walk(starlette_app.routes)

    # Print table header
    col_w = (20, 50, 30)
    header = f"{'Method':<{col_w[0]}} {'Path':<{col_w[1]}} {'Name':<{col_w[2]}}"
    typer.echo(header)
    typer.echo("-" * (sum(col_w) + 2))
    for method, path, name in collected:
        typer.echo(f"{method:<{col_w[0]}} {path:<{col_w[1]}} {name:<{col_w[2]}}")


@app.command()
def info(
    app_path: str = typer.Option(
        ..., "--app", help="Path to the Python file containing the Zeno app"
    ),
):
    """Show information about the Zeno application."""
    zeno_app, _ = _load_app(app_path)

    try:
        cinder_version = importlib.metadata.version("cinder")
    except importlib.metadata.PackageNotFoundError:
        cinder_version = "development"

    # Mask password in DB URL: ://user:pass@ -> ://***:***@
    db_url = zeno_app.database or ""
    db_masked = re.sub(r"://([^:@]+):([^@]+)@", "://***:***@", db_url)

    collections = list(getattr(zeno_app, "_collections", {}).keys())
    auth = getattr(zeno_app, "_auth", None)
    storage = getattr(zeno_app, "_storage_backend", None)
    broker = getattr(zeno_app, "_broker", None)
    auth_status = "enabled" if auth else "disabled"
    storage_type = type(storage).__name__ if storage else "not configured"
    broker_type = type(broker).__name__

    typer.echo(f"Title:            {zeno_app.title}")
    typer.echo(f"Version:          {zeno_app.version}")
    typer.echo(f"Python version:   {sys.version}")
    typer.echo(f"Cinder version:   {cinder_version}")
    typer.echo(f"Database:         {db_masked}")
    typer.echo(
        f"Collections ({len(collections)}):  {', '.join(collections) if collections else '(none)'}"
    )
    typer.echo(f"Auth:             {auth_status}")
    typer.echo(f"Storage:          {storage_type}")
    typer.echo(f"Realtime broker:  {broker_type}")


# ---------------------------------------------------------------------------
# migrate sub-app
# ---------------------------------------------------------------------------


def _get_db_url_for_migrate(app_path: Optional[str]) -> tuple[str, object | None]:
    """Return (db_url, zeno_app_or_None) for migrate commands."""
    if app_path is not None:
        zeno_app, _ = _load_app(app_path)
        return zeno_app.database, zeno_app
    url = (
        os.environ.get("CINDER_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "app.db"
    )
    return url, None


def _migrate_run(app_path: Optional[str], migrations_dir: str) -> None:
    """Apply all pending migrations (shared logic for callback and run sub-command)."""
    from zeno.db.connection import Database
    from zeno.migrations.engine import MigrationEngine

    db_url, _ = _get_db_url_for_migrate(app_path)

    async def _run():
        db = Database(db_url)
        await db.connect()
        try:
            engine = MigrationEngine(db, migrations_dir)
            applied = await engine.run_pending()
            if applied:
                for m in applied:
                    typer.echo(f"Applied: {m.id}")
            else:
                typer.echo("Nothing to migrate.")
        finally:
            await db.disconnect()

    asyncio.run(_run())


@migrate_app.callback(invoke_without_command=True)
def migrate(
    ctx: typer.Context,
    app_path: Optional[str] = typer.Option(
        None, "--app", help="Path to the Python file containing the Zeno app"
    ),
    migrations_dir: str = typer.Option(
        "migrations", "--dir", help="Directory containing migration files"
    ),
):
    """Apply pending migrations (default action)."""
    if ctx.invoked_subcommand is None:
        _migrate_run(app_path, migrations_dir)


@migrate_app.command("run")
def migrate_run(
    app_path: Optional[str] = typer.Option(
        None, "--app", help="Path to the Python file containing the Zeno app"
    ),
    migrations_dir: str = typer.Option(
        "migrations", "--dir", help="Directory containing migration files"
    ),
):
    """Apply all pending migrations."""
    _migrate_run(app_path, migrations_dir)


@migrate_app.command("status")
def migrate_status(
    app_path: Optional[str] = typer.Option(
        None, "--app", help="Path to the Python file containing the Zeno app"
    ),
    migrations_dir: str = typer.Option(
        "migrations", "--dir", help="Directory containing migration files"
    ),
):
    """Show the status of all migrations."""
    from zeno.db.connection import Database
    from zeno.migrations.engine import MigrationEngine

    db_url, _ = _get_db_url_for_migrate(app_path)

    async def _status():
        db = Database(db_url)
        await db.connect()
        try:
            engine = MigrationEngine(db, migrations_dir)
            rows = await engine.status()
            col_w = (40, 10, 30)
            header = (
                f"{'ID':<{col_w[0]}} {'Status':<{col_w[1]}} {'Applied At':<{col_w[2]}}"
            )
            typer.echo(header)
            typer.echo("-" * (sum(col_w) + 2))
            for row in rows:
                applied_at = row["applied_at"] or "-"
                typer.echo(
                    f"{row['id']:<{col_w[0]}} {row['status']:<{col_w[1]}} {applied_at:<{col_w[2]}}"
                )
        finally:
            await db.disconnect()

    asyncio.run(_status())


@migrate_app.command("rollback")
def migrate_rollback(
    app_path: Optional[str] = typer.Option(
        None, "--app", help="Path to the Python file containing the Zeno app"
    ),
    migrations_dir: str = typer.Option(
        "migrations", "--dir", help="Directory containing migration files"
    ),
):
    """Roll back the last applied migration."""
    from zeno.db.connection import Database
    from zeno.migrations.engine import MigrationEngine

    db_url, _ = _get_db_url_for_migrate(app_path)

    async def _rollback():
        db = Database(db_url)
        await db.connect()
        try:
            engine = MigrationEngine(db, migrations_dir)
            rolled_back = await engine.rollback()
            if rolled_back:
                typer.echo(f"Rolled back: {rolled_back.id}")
            else:
                typer.echo("No applied migrations to rollback.")
        finally:
            await db.disconnect()

    asyncio.run(_rollback())


@migrate_app.command("create")
def migrate_create(
    name: str = typer.Argument(..., help="Name of the migration"),
    app_path: Optional[str] = typer.Option(
        None, "--app", help="Path to the Python file containing the Zeno app"
    ),
    migrations_dir: str = typer.Option(
        "migrations", "--dir", help="Directory containing migration files"
    ),
    auto: bool = typer.Option(
        False, "--auto", help="Auto-generate migration from schema diff"
    ),
):
    """Create a new migration file."""
    from zeno.migrations.generator import (
        generate_migration_content,
        write_migration_file,
    )

    if not auto:
        content = generate_migration_content(name=name)
        filepath = write_migration_file(migrations_dir, name, content)
        typer.echo(f"Created migration: {filepath}")
        return

    # Auto mode: diff the schema
    from zeno.db.connection import Database
    from zeno.migrations.diff import SchemaComparator

    db_url, zeno_app = _get_db_url_for_migrate(app_path)
    if zeno_app is None:
        typer.echo("Error: --app is required for --auto", err=True)
        raise typer.Exit(1)

    collections = [col for col, _ in zeno_app._collections.values()]

    async def _auto_create():
        db = Database(db_url)
        await db.connect()
        try:
            comparator = SchemaComparator(db, collections)
            ops = await comparator.diff()
            content = generate_migration_content(ops, name)
            filepath = write_migration_file(migrations_dir, name, content)
            typer.echo(f"Created migration: {filepath}")
        finally:
            await db.disconnect()

    asyncio.run(_auto_create())


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

SUPPORTED_PLATFORMS = ("docker", "railway", "render", "fly")


def _detect_platform() -> str:
    """Auto-detect the deployment platform from environment variables."""
    if os.getenv("RAILWAY_ENVIRONMENT"):
        return "railway"
    if os.getenv("RENDER"):
        return "render"
    if os.getenv("FLY_APP_NAME"):
        return "fly"
    return "docker"


@app.command()
def deploy(
    platform: Optional[str] = typer.Option(
        None, "--platform", "-p",
        help=f"Target platform: {', '.join(SUPPORTED_PLATFORMS)}",
    ),
    app_path: str = typer.Option("main.py", "--app", help="Path to Cinder app file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview files without writing"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
):
    """Generate deployment configuration files for your Cinder app."""
    from zeno.deploy.config import generate_cinder_toml
    from zeno.deploy.introspect import introspect
    from zeno.deploy.platforms import PLATFORMS

    # Resolve platform
    chosen = platform or _detect_platform()
    if chosen not in PLATFORMS:
        typer.echo(
            f"Error: Unknown platform '{chosen}'. Choose from: {', '.join(SUPPORTED_PLATFORMS)}",
            err=True,
        )
        raise typer.Exit(1)

    # Introspect the app
    path = Path(app_path).resolve()
    if not path.exists():
        typer.echo(f"Error: File not found: {app_path}", err=True)
        raise typer.Exit(1)

    try:
        profile = introspect(app_path)
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    # Warn about SQLite on PaaS
    if profile.needs_sqlite and chosen != "docker":
        typer.echo(
            "Warning: SQLite is not recommended for production on cloud platforms. "
            "Consider switching to PostgreSQL.",
            err=True,
        )

    # Generate platform files
    output_dir = path.parent
    generator = PLATFORMS[chosen](profile, output_dir)
    files = generator.generate()

    # Also generate cinder.toml
    files.append(
        type(files[0])("cinder.toml", generate_cinder_toml(profile, chosen))
    )

    if dry_run:
        for f in files:
            typer.echo(f"\n{'=' * 60}")
            typer.echo(f"  {f.path}")
            typer.echo(f"{'=' * 60}")
            typer.echo(f.content)
        typer.echo(f"\n{len(files)} file(s) would be generated.")
        return

    # Write files
    written = 0
    for f in files:
        dest = output_dir / f.path
        if dest.exists() and not force:
            overwrite = typer.confirm(f"  {f.path} already exists. Overwrite?")
            if not overwrite:
                typer.echo(f"  Skipped: {f.path}")
                continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f.content, encoding="utf-8")
        typer.echo(f"  Created: {f.path}")
        written += 1

    typer.echo(f"\n{written} file(s) generated for {chosen}.")

    # Show post-generation instructions if available
    if hasattr(generator, "post_generate_instructions"):
        typer.echo("")
        typer.echo(generator.post_generate_instructions())
