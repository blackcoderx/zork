---
title: Access Control
description: Fine-grained permission rules for every collection
---

Cinder uses a simple string-based rule system to control who can read and write each collection. Rules are declared when you call `app.register()`.

## Rule syntax

Rules follow the pattern `{operation}:{role}`:

```python
app.register(posts, auth=["read:public", "write:authenticated"])
```

## Available rules

| Rule | Who can access |
|------|----------------|
| `read:public` | Anyone, no token required |
| `read:authenticated` | Any logged-in user |
| `read:owner` | The user who created the record (`created_by` field must match) |
| `read:admin` | Users with `role = "admin"` |
| `write:public` | Anyone, no token required |
| `write:authenticated` | Any logged-in user |
| `write:owner` | The user who created the record |
| `write:admin` | Users with `role = "admin"` |

`read` covers `GET /api/{collection}` and `GET /api/{collection}/{id}`.
`write` covers `POST`, `PATCH`, and `DELETE`.

## Examples

**Public blog** — anyone can read, authenticated users can write:
```python
app.register(posts, auth=["read:public", "write:authenticated"])
```

**Private notes** — owner-only access:
```python
app.register(notes, auth=["read:owner", "write:owner"])
```

**Admin-only** — only admins can read or write:
```python
app.register(audit_logs, auth=["read:admin", "write:admin"])
```

**No auth** — fully public (same as omitting the `auth` parameter):
```python
app.register(public_data)
```

## The `created_by` field

When `owner` rules are used, Cinder automatically adds a `created_by` column to the collection if one does not already exist. On `POST`, the authenticated user's ID is stored in that field. The ownership check on `read:owner` and `write:owner` compares `created_by` against the token's subject.

You can declare the field explicitly if you need to customise it:

```python
notes = Collection("notes", fields=[
    TextField("body"),
    TextField("created_by"),  # explicit — will not be added twice
])
app.register(notes, auth=["read:owner", "write:owner"])
```

## Promoting users to admin

Use the CLI to grant admin access:

```bash
cinderapi promote alice@example.com
cinderapi promote bob@example.com --role moderator
```

Or update the `_users` table directly.

## Combining rules

You can have separate read and write rules. Not all combinations are useful, but they are all valid:

```python
# Admins write, everyone reads
app.register(announcements, auth=["read:public", "write:admin"])

# Owners write, authenticated users read
app.register(profiles, auth=["read:authenticated", "write:owner"])
```

Only one rule per operation is applied. If you need more complex logic, use [Lifecycle Hooks](/core-concepts/lifecycle-hooks/) to inspect `ctx.user` and raise a `CinderError(403, "Forbidden")`.
