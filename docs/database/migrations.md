# Database Migrations

Zork includes a migrations system for managing database schema changes over time. This guide explains how to create, run, and manage migrations.

## When to Use Migrations

Use migrations for:

- Creating database indexes
- Dropping columns
- Renaming columns
- Changing column types
- Complex schema changes
- Version-controlled schema changes

For simple additive changes (adding new fields), Zork's auto-sync handles this automatically on startup.

## Migration Files

Migration files are Python files stored in a `migrations/` directory:

```
migrations/
├── 20240115_100000_create_posts_table.py
├── 20240116_143022_add_index_to_posts.py
└── 20240120_090000_add_published_at_column.py
```

## Creating Migrations

### Create a Blank Migration

```bash
zork migrate create add_status_column
```

This creates `migrations/20240120_090000_add_status_column.py`:

```python
"""Add status column"""

async def up(db):
    pass

async def down(db):
    pass
```

### Auto-Generate from Schema

Compare your current schema against the database and generate migration automatically:

```bash
zork migrate create add_new_fields --app main.py --auto
```

This compares your collection definitions with the live database and creates the appropriate migration.

## Writing Migrations

### Adding a Column

```python
"""Add published_at column to posts"""

async def up(db):
    await db.execute("""
        ALTER TABLE posts ADD COLUMN published_at TEXT
    """)

async def down(db):
    await db.execute("""
        ALTER TABLE posts DROP COLUMN published_at
    """)
```

### Creating an Index

```python
"""Add index on posts.category"""

async def up(db):
    await db.execute("""
        CREATE INDEX idx_posts_category ON posts (category)
    """)

async def down(db):
    await db.execute("""
        DROP INDEX IF EXISTS idx_posts_category
    """)
```

### Dropping a Column

```python
"""Remove deprecated field"""

async def up(db):
    # SQLite doesn't support DROP COLUMN directly
    # You may need to recreate the table
    await db.execute("""
        CREATE TABLE posts_new AS SELECT id, title, body, created_at, updated_at FROM posts
    """)
    await db.execute("DROP TABLE posts")
    await db.execute("ALTER TABLE posts_new RENAME TO posts")

async def down(db):
    await db.execute("""
        ALTER TABLE posts ADD COLUMN deprecated_field TEXT
    """)
```

### Complex Migrations

```python
"""Split name into first_name and last_name"""

async def up(db):
    # Add new columns
    await db.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
    await db.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
    
    # Migrate data
    await db.execute("""
        UPDATE users SET 
            first_name = SUBSTR(name, 1, INSTR(name || ' ', ' ') - 1),
            last_name = SUBSTR(name, INSTR(name, ' ') + 1)
        WHERE name IS NOT NULL
    """)

async def down(db):
    # Combine back
    await db.execute("""
        UPDATE users SET 
            name = COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')
    """)
    await db.execute("ALTER TABLE users DROP COLUMN first_name")
    await db.execute("ALTER TABLE users DROP COLUMN last_name")
```

## Running Migrations

### Run All Pending Migrations

```bash
zork migrate run
```

Or with an app file:

```bash
zork migrate run --app main.py
```

### Check Status

View all migrations and their status:

```bash
zork migrate status
```

Example output:

```
ID                                       Status    Applied At
---------------------------------------- --------- ---------------------------
20240115_100000_create_posts_table      applied   2024-01-15T10:00:00Z
20240116_143022_add_index_to_posts      applied   2024-01-16T14:30:00Z
20240120_090000_add_status_column        pending
```

### Rollback

Roll back the last applied migration:

```bash
zork migrate rollback
```

This runs the `down` function of the most recent migration.

## Migration Directory

By default, migrations are stored in a `migrations/` directory. You can specify a different location:

```bash
zork migrate run --dir db/migrations
```

## How Migrations Work

### The Migrations Table

Zork creates a `_schema_migrations` table to track applied migrations:

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Migration ID (filename without extension) |
| `applied_at` | TEXT | ISO timestamp when applied |

### Execution Order

Migrations run in filename order. The timestamp prefix ensures correct ordering:

```
20240115_100000_migration_a.py  # Runs first
20240115_110000_migration_b.py  # Runs second
20240116_090000_migration_c.py  # Runs third
```

### Idempotency

The same migration should not be applied twice. Zork tracks applied migrations and skips already-applied ones.

## Auto-Sync vs Migrations

| Feature | Auto-Sync | Migrations |
|---------|-----------|------------|
| Add tables | Yes | Yes |
| Add columns | Yes | Yes |
| Drop columns | No | Yes |
| Create indexes | No | Yes |
| Rename columns | No | Yes |
| Data transforms | No | Yes |
| Requires explicit tracking | No | Yes |

## Best Practices

### Keep Migrations Small

Each migration should do one thing. This makes rollback easier and reduces risk.

### Always Write the Down Migration

Even if you think you will never need to rollback, write the `down` function anyway.

### Test Migrations

Before deploying, test your migrations on a copy of production data.

### Use Transactions (Carefully)

Some databases support transactional DDL. Note that SQLite does not support this.

## Environment-Specific Migrations

For environment-specific changes, use conditional logic:

```python
"""Add analytics tables"""

async def up(db):
    # Check if we're using PostgreSQL
    if "postgresql" in str(db.url):
        await db.execute("CREATE TABLE analytics (...)")
    # SQLite doesn't get this table
```

## Next Steps

- [Database Overview](/database/overview) — Database configuration
- [Schema Auto-Sync](/core-concepts/collections) — Automatic schema updates
