# Cinder

A lightweight, open-source backend framework for Python developers. Build production-ready REST APIs with built-in auth and dynamic collections — without depending on FastAPI or any heavy framework.

## Install

```bash
pip install cinder
```

## Quick Start

```python
from cinder import Cinder, Collection, TextField, IntField, Auth

app = Cinder(database="app.db")

posts = Collection("posts", fields=[
    TextField("title", required=True),
    TextField("body"),
    IntField("views", default=0),
])

auth = Auth(token_expiry=86400, allow_registration=True)

app.register(posts, auth=["read:public", "write:authenticated"])
app.use_auth(auth)
app.serve()
```

```bash
cinder serve main.py
# REST API running at http://localhost:8000
```

## Features

- Dynamic collections with auto-generated CRUD API
- Built-in JWT auth with role-based access control
- SQLite persistence (zero setup)
- Schema auto-sync on startup
- CORS, Request ID, and error handling middleware
- CLI: `cinder serve`, `cinder init`, `cinder promote`

## License

MIT
