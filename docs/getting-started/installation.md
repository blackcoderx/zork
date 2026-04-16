# Installation

This guide walks you through installing Zork and its optional dependencies.

## Requirements

Before installing Zork, make sure you have:

- Python 3.11 or higher
- pip or uv package manager

You can check your Python version by running:

```bash
python --version
```

## Install Zork

Install the core Zork package using pip:

```bash
pip install zork
```

Or using uv (recommended for faster installs):

```bash
uv add zork
```

The core package includes SQLite support out of the box. No additional configuration is needed to get started.

## Optional Dependencies

Zork uses optional dependency groups to keep the core installation minimal. Install only what you need.

### Available Extras

| Extra | Installs | Use Case |
|-------|----------|----------|
| `postgres` | asyncpg | PostgreSQL databases |
| `mysql` | aiomysql | MySQL and MariaDB databases |
| `s3` | boto3 | S3-compatible file storage (AWS, R2, MinIO, etc.) |
| `email` | aiosmtplib | Sending emails via SMTP |
| `redis` | redis | Caching, rate limiting, and realtime scaling |
| `all` | All of the above | Full-featured installation |

### Installing Extras

Install a single extra:

```bash
pip install "zork[postgres]"
```

Install multiple extras:

```bash
pip install "zork[postgres,redis,email]"
```

Using uv:

```bash
uv add "zork[postgres,redis,email]"
```

Install everything:

```bash
pip install "zork[all]"
```

## Verifying Installation

After installation, verify that Zork is installed correctly by checking the version:

```bash
zork --version
```

You should see the Zork version printed in your terminal. If you see a "command not found" error, ensure your Python environment's bin directory is on your PATH.

## Creating a New Project

The quickest way to start a new Zork project is to use the built-in project scaffold:

```bash
zork init myapp
cd myapp
```

This creates a new directory called `myapp` with the following files:

- `main.py` — Your application entry point
- `.env` — Environment variables (add your secrets here)
- `.gitignore` — Git ignore rules for common files

The generated `main.py` contains a basic Zork application with authentication:

```python
from zork import Zork, Collection, TextField, IntField, Auth

app = Zork(database="app.db")

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
```

## Next Steps

Now that Zork is installed, continue to the [Quick Start](/getting-started/quick-start) guide to build your first API.
