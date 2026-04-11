---
title: Relations
description: Foreign key references between collections
---

`RelationField` creates a typed reference from one collection to another. Relations are stored as the referenced record's UUID and can be expanded on demand.

## Quick example

```python
from cinder import Collection, TextField, RelationField

users = Collection("users", fields=[
    TextField("name", required=True),
])

comments = Collection("comments", fields=[
    TextField("body", required=True),
    RelationField("author", collection="users"),
    RelationField("post", collection="posts", required=True),
])
```

## RelationField options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `name` | `str` | — | Column name in the database |
| `collection` | `str` | — | Name of the target collection |
| `required` | `bool` | `False` | Field cannot be null |
| `unique` | `bool` | `False` | Enforce a UNIQUE constraint |
| `indexed` | `bool` | `False` | Create a database index (recommended for FK columns) |

## Storing a relation

Send the ID of the referenced record:

```bash
POST /api/comments
{
  "body": "Great post!",
  "author": "user-uuid",
  "post": "post-uuid"
}
```

## Expanding a relation

By default the API returns the raw ID:

```json
{ "id": "...", "body": "Great post!", "author": "user-uuid" }
```

Add `?expand=field` to fetch the full related record. The expanded data is placed in a nested `expand` key — the original ID field remains unchanged:

```
GET /api/comments?expand=author
```

```json
{
  "items": [
    {
      "id": "...",
      "body": "Great post!",
      "author": "user-uuid",
      "expand": {
        "author": {
          "id": "user-uuid",
          "name": "Alice"
        }
      }
    }
  ]
}
```

Expand multiple fields:

```
GET /api/comments?expand=author,post
```

Expand on a single record:

```
GET /api/comments/some-id?expand=author
```

## Indexing relation fields

For collections with many records, add `indexed=True` to relation fields you filter or sort on:

```python
RelationField("author", collection="users", indexed=True)
```

This creates a `CREATE INDEX` on the column, making queries like `?filter[author]=user-id` significantly faster.

## Many-to-many relations

Cinder does not have a built-in many-to-many field. Model these with a junction collection:

```python
post_tags = Collection("post_tags", fields=[
    RelationField("post", collection="posts", required=True, indexed=True),
    RelationField("tag", collection="tags", required=True, indexed=True),
])
```

## Orphaned references

There is no database-level referential integrity enforced by default. Deleting a referenced record leaves orphaned IDs in child records. Handle this with [Lifecycle Hooks](/core-concepts/lifecycle-hooks/) on the parent collection's `after_delete` event if you need cascade-style cleanup.
