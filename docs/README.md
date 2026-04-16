# Zork Documentation

Welcome to the Zork documentation. Zork is a lightweight, open-source backend framework for Python that auto-generates REST APIs with authentication, file storage, realtime support, and more from simple Python schema definitions.

## Getting Started

New to Zork? Start here:

- [Installation](/getting-started/installation) — Install Zork and its dependencies
- [Quick Start](/getting-started/quick-start) — Build your first API in under 10 minutes
- [Project Structure](/getting-started/project-structure) — Understanding the CLI and project layout

## Core Concepts

Learn the fundamental building blocks of Zork:

- [The App](/core-concepts/app) — The Zork application class and its configuration methods
- [Collections](/core-concepts/collections) — Defining data schemas that become REST APIs
- [Field Types](/core-concepts/fields) — All available field types and their options
- [Relations](/core-concepts/relations) — Linking collections together with RelationField
- [Lifecycle Hooks](/core-concepts/lifecycle-hooks) — Running code before and after operations
- [Middleware Stack](/core-concepts/middleware-stack) — How requests flow through Zork
- [Error Handling](/core-concepts/errors) — Handling and raising errors

## Authentication

Add user authentication to your application:

- [Setup](/authentication/setup) — Configuring authentication for your app
- [User Model](/authentication/user-model) — The users table and extending it
- [Auth Endpoints](/authentication/endpoints) — Registration, login, logout, and more
- [Security](/authentication/security) — JWT tokens, blocklists, and CSRF protection

## Database

Store your data with support for multiple database engines:

- [Database Overview](/database/overview) — Multi-database support and configuration
- [Migrations](/database/migrations) — Managing schema changes over time

## File Storage

Handle file uploads with pluggable storage backends:

- [Setup](/file-storage/setup) — Configuring file storage
- [Storage Providers](/file-storage/providers) — Local storage, S3, R2, MinIO, and more

## Email

Send transactional emails:

- [Email Setup](/email/setup) — Configuring SMTP and email providers

## Realtime

Add real-time capabilities to your application:

- [Realtime Overview](/realtime/overview) — WebSocket and Server-Sent Events

## Caching

Improve performance with caching:

- [Caching Setup](/caching/setup) — Memory and Redis caching backends

## Rate Limiting

Protect your API from abuse:

- [Rate Limiting Setup](/rate-limiting/setup) — Configuring rate limits

## API Reference

Understand the generated API:

- [Endpoints](/api/endpoints) — CRUD routes, filtering, and pagination
- [OpenAPI](/api/openapi) — Auto-generated API documentation

## Deployment

Deploy your Zork application:

- [Deployment Overview](/deployment/overview) — Deploy to Docker, Railway, Render, and Fly.io

## Guides

Step-by-step tutorials:

- [Troubleshooting](/guides/troubleshooting) — Common issues and solutions

---

## Quick Example

Here is a minimal Zork application that creates a blog API with authentication:

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
app.serve()
```

Running this gives you:

- User registration and login at `/api/auth/*`
- Full CRUD for posts at `/api/posts`
- JWT authentication
- OpenAPI documentation at `/docs`

---

## Additional Resources

- [GitHub Repository](https://github.com/blackcoderx/zork)
- [PyPI Package](https://pypi.org/project/zork/)
