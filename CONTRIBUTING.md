# Contributing to Cinder

Thanks for taking the time to contribute. Cinder is a small, focused project and contributions of all sizes are welcome — bug fixes, new features, docs improvements, or test coverage.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Making Changes](#making-changes)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Reporting Bugs](#reporting-bugs)
- [Code Style](#code-style)

---

## Getting Started

Cinder uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# 1. Fork and clone the repo
git clone https://github.com/your-username/cinder
cd cinder

# 2. Install dependencies (including dev extras)
uv sync --all-extras

# 3. Verify everything works
uv run pytest
```

---

## Project Structure

```
cinder/
├── src/cinder/         # Framework source code
│   ├── app.py          # Cinder app entry point
│   ├── collections/    # Collection and field definitions
│   ├── auth/           # JWT auth, user model, endpoints
│   ├── db/             # Database adapters (SQLite, PostgreSQL, MySQL)
│   ├── hooks/          # Lifecycle hook system
│   ├── realtime/       # WebSocket and SSE
│   ├── storage/        # File storage backends
│   ├── cache/          # Caching backends
│   ├── ratelimit/      # Rate limiting
│   ├── email/          # Email backends
│   ├── migrations/     # Schema migration engine
│   ├── openapi.py      # OpenAPI 3.1 generation
│   └── cli.py          # CLI commands (cinderapi serve, migrate, etc.)
├── tests/              # Pytest test suite
├── web/                # Docs site (Astro + Starlight)
└── pyproject.toml
```

---

## Running Tests

```bash
# Run the full test suite
uv run pytest

# Run a specific test file
uv run pytest tests/test_auth.py

# Run with output
uv run pytest -v

# Run tests matching a keyword
uv run pytest -k "cache"
```

Tests use `pytest-asyncio` for async test cases and `fakeredis` for Redis-dependent tests — no real Redis instance required.

---

## Making Changes

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Write tests first** if you're adding new behaviour. Test files live in `tests/` and follow the naming pattern `test_<module>.py`.

3. **Keep changes focused.** One feature or fix per pull request makes review faster.

4. **Update the docs** if your change affects user-facing behaviour. Docs live in `web/src/content/docs/` and are written in Markdown/MDX.

---

## Submitting a Pull Request

1. Make sure all tests pass:
   ```bash
   uv run pytest
   ```

2. Push your branch and open a PR against `main`.

3. Fill out the PR description with:
   - What the change does
   - Why it's needed
   - Any relevant issue numbers

---

## Reporting Bugs

Open an issue and include:

- Cinder version (`pip show cinder`)
- Python version (`python --version`)
- Minimal reproduction case
- Full error traceback if applicable

---

## Code Style

- Follow existing patterns in the codebase — consistency matters more than personal preference.
- Use type hints.
- Keep functions small and focused.
- Async all the way down — Cinder is fully async; avoid blocking calls.

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
