---
title: Installation
description: Install Cinder and its optional dependencies
sidebar:
  order: 1
---

## Requirements

- Python 3.11 or higher
- pip or [uv](https://docs.astral.sh/uv/)

## Install

```bash
pip install cinder
```

With [uv](https://docs.astral.sh/uv/):

```bash
uv add cinder
```

This installs the core framework with SQLite support. No extra configuration needed to get started.

## Optional Dependencies

Cinder uses extras for optional features to keep the core installation minimal.

| Extra | Installs | When to use |
|-------|----------|-------------|
| `[postgres]` | asyncpg | PostgreSQL databases |
| `[mysql]` | aiomysql | MySQL / MariaDB databases |
| `[s3]` | boto3 | S3-compatible file storage (AWS, R2, MinIO, etc.) |
| `[email]` | aiosmtplib | SMTP email delivery |
| `[redis]` | redis | Caching, rate limiting, and realtime at scale |

Install extras:

```bash
# Single extra
pip install "cinder[postgres]"

# Multiple extras
pip install "cinder[postgres,redis,email]"
```

With uv:

```bash
uv add "cinder[postgres,redis,email]"
```

## Scaffold a new project

Use the CLI to create a project with a starter layout:

```bash
cinder init myapp
cd myapp
```

This creates `main.py`, `.env`, and `.gitignore` with sensible defaults.

## Verify the installation

```bash
cinder --version
```

You should see the Cinder version printed. If you see a "command not found" error, ensure your Python environment's `bin` directory is on your `PATH`.
