---
title: Schema Auto-Sync
description: How Cinder keeps your database schema in sync with your code
---

Every time you start a Cinder app, it compares each registered `Collection` against the live database schema and applies any safe, non-destructive changes automatically.

## What auto-sync does

On startup, for each collection Cinder will:

1. **Create the table** if it doesn't exist yet
2. **Add new columns** for any fields in your `Collection` that are not in the database
3. **Add new indexes** for fields with `indexed=True` or entries in `Collection.indexes`

## What auto-sync does NOT do

Auto-sync is intentionally conservative:

- **Columns are never dropped** — removing a field from your `Collection` leaves the column in the database
- **Columns are never renamed** — if you rename a field, auto-sync adds a new column; the old one stays
- **Column types are not changed** — altering a column type requires a migration

This ensures you never accidentally lose production data due to a code change.

## When to use migrations instead

Use [Migrations](/migrations/commands/) when you need to:

- Rename a column
- Drop a column
- Change a column type
- Apply a custom SQL transformation to existing data
- Coordinate a schema change with a specific deployment

## Schema drift in production

For production deployments, the recommended approach is to use explicit migrations (run `cinderapi migrate`) and rely on auto-sync only for convenience during local development.

You can still use auto-sync in production for additive changes — new fields are always safe. But any destructive or transformative schema change must go through a migration.

## Disabling auto-sync

Auto-sync is not currently configurable — it always runs on startup. For strict migration-only workflows, ensure your collections don't introduce new columns outside of migration files.
