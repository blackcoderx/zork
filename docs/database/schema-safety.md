# Schema Safety

This guide explains Zork's schema safety features and best practices for managing database schema changes in different environments.

## Overview

Zork's schema management balances two goals:

- **Fast development** through auto-sync
- **Safe production** through explicit migrations

Understanding when to use each mode helps you avoid data loss and schema drift.

## Environment Modes

### Development

In development, auto-sync provides fast feedback:

- Add a field to your collection, and the column appears immediately
- Add a collection, and the table is created
- Add an index, and it is created automatically

This works well for local development where the database is disposable and you want rapid iteration.

### Production

In production, explicit is better than implicit:

- No surprise schema changes
- Version-controlled changes
- Rollback capability
- Team visibility

Auto-sync is disabled by default for PostgreSQL and MySQL databases.

## Default Behavior

Zork automatically detects the appropriate mode based on your database:

| Database Type | Auto-Sync Default |
|--------------|-------------------|
| SQLite (bare path like `app.db`) | Enabled |
| PostgreSQL | Disabled |
| MySQL | Disabled |

This means you do not need to configure anything for local development with SQLite. When you switch to PostgreSQL or MySQL, auto-sync is automatically disabled.

## Safety Features

### Schema Diff

Preview changes without applying them:

```bash
zork schema diff --app main.py
```

Example output:

```
Collection: posts
  + Column: status (TEXT)           Would be added
  + Column: views (INTEGER)          Would be added
  + Index: idx_posts_status        Would be created
```

### Migration Sync

Convert auto-sync decisions to migrations:

```bash
zork migrate sync --app main.py
```

This creates migration files that you can review and commit to version control.

### Orphan Detection

Zork warns when columns exist in the database but not in your schema:

```
WARNING: Column 'body' exists in table 'posts' but is not defined in the schema.
  → This column will not be used by Zork
  → Run `zork migrate sync --include-orphans` to generate a drop migration
```

Orphan columns are never automatically deleted. You must explicitly create a migration to drop them.

### Typo Detection

Zork detects potential typos:

```
Collection: posts
  + Column: title (TEXT)              Would be added
  ~ Possible typo: 'titile' looks like 'title'
    → Check if 'titile' should be renamed to 'title'
```

If you see a typo warning, investigate whether:

- The field name in your collection has a typo
- The database column was accidentally created with a typo
- Both should be renamed to the correct spelling

## Configuration

### Environment Variable

```bash
ZORK_AUTO_SYNC=false
```

### App Configuration

```python
app = Zork(
    database="postgresql://user:pass@host:5432/mydb",
    auto_sync=False,
)
```

### Checking Current Setting

```bash
zork info --app main.py
```

This shows whether auto-sync is enabled for your application.

## Migration Workflow

### Step 1: Make Schema Changes

Edit your collections in `main.py`:

```python
posts = Collection("posts", fields=[
    TextField("title", required=True),
    TextField("body"),
    TextField("status"),  # New field
])
```

### Step 2: Preview Changes

Run schema diff to see what would change:

```bash
zork schema diff --app main.py
```

### Step 3: Generate Migrations

Convert changes to migration files:

```bash
zork migrate sync --app main.py
```

This creates:

```
migrations/
├── 20260416_120000_add_status_column.py
```

### Step 4: Review Migrations

Always review generated migrations before running them:

```bash
cat migrations/20260416_120000_add_status_column.py
```

### Step 5: Run Migrations

Apply the migrations:

```bash
zork migrate run --app main.py
```

## Handling Orphans

Orphan columns appear when:

- A field was removed from your collection
- A typo created an extra column
- Manual database changes were made

### Investigation

First, understand why the orphan exists:

```bash
zork schema diff --app main.py --verbose
```

### Options

**Keep the column**

If the data is valuable, keep the column. It will not affect Zork operations but also will not be used.

**Drop via migration**

Generate a drop migration:

```bash
zork migrate sync --include-orphans --app main.py
```

Review and run the migration:

```bash
zork migrate run --app main.py
```

**Migrate to new field**

If the orphan has valuable data, migrate it first:

```python
# In a hook or custom migration
await db.execute("""
    UPDATE posts SET title = titile WHERE title IS NULL AND titile IS NOT NULL
""")
```

Then drop the orphan column.

## Common Scenarios

### Adding a New Field

1. Add the field to your collection
2. Run `zork schema diff` to preview
3. Run `zork migrate sync` to create migration
4. Run `zork migrate run` to apply

### Renaming a Field

Renaming requires multiple steps:

1. Add the new column (e.g., `title`)
2. Migrate data from old column (e.g., `titile`)
3. Drop the old column

```bash
zork migrate sync --app main.py
# Manually edit migration to add data migration
zork migrate run --app main.py
```

### Removing a Field

1. Remove the field from your collection
2. Run `zork schema diff` — orphan warning appears
3. Run `zork migrate sync --include-orphans` to generate drop migration
4. Review migration carefully (data will be lost)
5. Run `zork migrate run`

## Production Checklist

Before deploying to production:

- [ ] Disable auto-sync (`ZORK_AUTO_SYNC=false`)
- [ ] Run `zork schema diff` to review pending changes
- [ ] Generate migrations with `zork migrate sync`
- [ ] Review all generated migrations
- [ ] Test migrations on a staging database
- [ ] Commit migrations to version control
- [ ] Run migrations as part of deployment

## Best Practices

1. **Use migrations for production**
   Auto-sync is convenient but risky with real data.

2. **Test migrations locally first**
   Always run migrations on a copy of production data before deploying.

3. **Keep migrations small**
   One change per migration makes rollback easier.

4. **Write reversible migrations**
   Include the `down` function whenever possible.

5. **Review generated migrations**
   Do not blindly run migrations you have not read.

6. **Commit migrations to version control**
   Everyone on the team should run the same migrations.

7. **Never manually edit production databases**
   Use migrations for all schema changes.

8. **Handle orphans explicitly**
   Do not ignore orphan warnings. Investigate and decide what to do.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ZORK_AUTO_SYNC` | Auto-detect | Enable or disable auto-sync |

## Troubleshooting

### "Auto-sync is enabled in production" warning

This warning appears when auto-sync is active with PostgreSQL or MySQL. To fix:

```bash
export ZORK_AUTO_SYNC=false
```

Or update your app configuration:

```python
app = Zork(database="postgresql://...", auto_sync=False)
```

### "Column already exists" error

This occurs when auto-sync tries to add a column that already exists with a different structure. Use migrations for this type of change.

### Migration fails on large table

Large tables may require special handling. Consider:

- Running during low-traffic periods
- Using batched updates for data migrations
- Adding new columns as nullable first

## Next Steps

- [Database Overview](/database/overview) — Database configuration
- [Database Migrations](/database/migrations) — Migration system reference
