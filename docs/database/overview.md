# Database Overview

Zork supports multiple database engines with a unified interface. This guide explains how to configure and use different databases.

## Default Configuration

By default, Zork uses SQLite with a file named `app.db`:

```python
from zork import Zork

app = Zork()  # Uses app.db by default
```

## Supported Databases

| Database | URL Format | Package Required |
|----------|-----------|------------------|
| SQLite | `app.db` or `sqlite:///path` | Built-in |
| PostgreSQL | `postgresql://...` | `zork[postgres]` |
| MySQL | `mysql://...` | `zork[mysql]` |

## SQLite

SQLite is the default and works great for development and small-scale deployments.

### Basic Usage

```python
app = Zork(database="app.db")
```

### With Path

```python
app = Zork(database="data/app.db")
app = Zork(database="sqlite:///data/app.db")
```

SQLite stores the entire database in a single file. It requires no separate server and is perfect for:

- Local development
- Small to medium applications
- Single-server deployments
- Applications with limited concurrent writes

## PostgreSQL

PostgreSQL is recommended for production deployments.

### Installation

```bash
pip install "zork[postgres]"
```

### Configuration

```python
app = Zork(database="postgresql://user:pass@localhost:5432/mydb")
```

### Full Configuration

```python
from zork.db.backends.postgresql import PostgreSQLBackend

app.configure_database(
    PostgreSQLBackend(
        url="postgresql://user:pass@localhost:5432/mydb",
        min_size=2,        # Minimum connections
        max_size=20,      # Maximum connections
    )
)
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ZORK_DATABASE_URL` | Database URL | `app.db` |
| `ZORK_DB_POOL_MIN` | Min connections | 1 |
| `ZORK_DB_POOL_MAX` | Max connections | 10 |
| `ZORK_DB_TIMEOUT` | Connection timeout | 30 |
| `ZORK_DB_CONNECT_TIMEOUT` | Connect timeout | 10 |

### URL Priority

The database URL is resolved in this order:

1. `ZORK_DATABASE_URL` environment variable
2. `DATABASE_URL` environment variable (for PaaS compatibility)
3. Constructor `database` argument
4. Default: `app.db`

## MySQL

MySQL is supported for existing MySQL/MariaDB infrastructure.

### Installation

```bash
pip install "zork[mysql]"
```

### Configuration

```python
app = Zork(database="mysql://user:pass@localhost:3306/mydb")
```

### Alternative Drivers

```python
# Using aiomysql (default)
app = Zork(database="mysql://user:pass@localhost:3306/mydb")

# Using asyncmy
app = Zork(database="mysql+asyncmy://user:pass@localhost:3306/mydb")
```

## Database URL Formats

### SQLite

```python
# Bare path (relative)
app = Zork(database="app.db")

# Bare path (absolute)
app = Zork(database="/var/data/app.db")

# With scheme
app = Zork(database="sqlite:///var/data/app.db")
```

### PostgreSQL

```python
# Standard
app = Zork(database="postgresql://user:pass@host:5432/db")

# Short form
app = Zork(database="postgres://user:pass@host:5432/db")

# Unix socket
app = Zork(database="postgresql://user:pass@/var/run/postgresql/db")
```

### MySQL

```python
# Standard
app = Zork(database="mysql://user:pass@host:3306/db")

# With alternative driver
app = Zork(database="mysql+aiomysql://user:pass@host:3306/db")
app = Zork(database="mysql+asyncmy://user:pass@host:3306/db")
```

## Pool Configuration

For production PostgreSQL/MySQL deployments, tune the connection pool:

```python
from zork.db.backends.postgresql import PostgreSQLBackend

app.configure_database(
    PostgreSQLBackend(
        url="postgresql://user:pass@host:5432/db",
        min_size=5,        # Keep at least 5 connections
        max_size=20,       # Max 20 concurrent connections
    )
)
```

Pool settings depend on your application workload and database server capacity.

## Switching Databases

You can switch databases without changing your application code by setting environment variables:

```bash
# Development (SQLite)
export DATABASE_URL=app.db

# Production (PostgreSQL)
export DATABASE_URL=postgresql://user:pass@host:5432/prod
```

## Schema Auto-Sync

When your application starts, Zork can automatically sync the database schema with your collection definitions.

### Default Behavior

| Database | Auto-Sync Default |
|----------|------------------|
| SQLite | Enabled |
| PostgreSQL | Disabled |
| MySQL | Disabled |

This means:

- SQLite development works without configuration
- PostgreSQL and MySQL require explicit migrations

### Configuration

To disable auto-sync for production:

```python
app = Zork(database="postgresql://...", auto_sync=False)
```

Or via environment variable:

```bash
ZORK_AUTO_SYNC=false
```

### When to Use

**Use auto-sync for:**

- Local development with SQLite
- Rapid prototyping
- Initial project setup

**Use migrations for:**

- Production databases
- Team development
- Any database with valuable data

### Previewing Changes

Before deploying, preview schema changes:

```bash
zork schema diff --app main.py
```

See [Schema Safety](/database/schema-safety) for the full guide.

## Checking Database Connectivity

Use the doctor command to verify database connectivity:

```bash
zork doctor --app main.py
```

Example output:

```
[OK] Database: postgresql://***:***@localhost:5432/mydb
```

## Next Steps

- [Schema Safety](/database/schema-safety) — Understanding schema management
- [Migrations](/database/migrations) — Managing schema changes
- [File Storage](/file-storage/setup) — Storing uploaded files
