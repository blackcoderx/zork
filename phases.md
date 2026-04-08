# Cinder — Future Phases Roadmap

> Phases 0-2 (Foundation, Collections, Auth) are complete. This document outlines the remaining phases that will layer on top without breaking changes.

---

## Phase 3: Hooks & Lifecycle Events ( Done)

**Goal:** Let developers run custom logic before/after CRUD operations and auth events.

**Key Features:**

- **Collection lifecycle hooks:**
  - `before_create(data)` — modify or validate data before insert
  - `after_create(record)` — trigger side effects after insert (e.g., send notification)
  - `before_update(record, changes)` — validate or transform updates
  - `after_update(record)` — trigger side effects after update
  - `before_delete(record)` — cancel delete via `CinderError.cancel_delete()`, implement soft deletes
  - `after_delete(record)` — cleanup related data

- **Auth lifecycle hooks:**
  - `on_register(user)` — post-registration logic (welcome email, default data)
  - `on_login(user)` — login tracking, audit logging
  - `on_logout(user)` — session cleanup
  - `on_password_reset(user)` — security notifications

- **Hook execution model:**
  - `before_*` hooks can modify data or raise `CinderError` to abort
  - `after_*` hooks receive the final record (read-only side effects)
  - Multiple hooks per event, executed in registration order
  - Async hooks supported

**Existing Infrastructure:**
- `Collection._hooks` dict and `.on(event, handler)` method already exist in `src/cinder/collections/schema.py`
- `Auth._hooks` dict and `.on(event, handler)` method already exist in `src/cinder/auth/__init__.py`
- `CinderError.cancel_delete()` sentinel already implemented in `src/cinder/errors.py`
- Only missing: wiring hooks into `src/cinder/collections/router.py`, `src/cinder/collections/store.py`, and `src/cinder/auth/routes.py`

**Files to Modify:**
- `src/cinder/collections/store.py` — call `before_*`/`after_*` hooks in CRUD methods
- `src/cinder/collections/router.py` — pass hook context (request, user) to store
- `src/cinder/auth/routes.py` — call auth hooks in register/login/logout/reset handlers

---

## Phase 4: File Storage ( Done)

**Goal:** Add file upload support with pluggable storage backends.

**Key Features:**

- **FileField** — new field type for file uploads
  - Configurable: `max_size`, `allowed_types` (MIME), `multiple` (single vs array)
  - Stores file metadata in SQLite, binary in storage backend
- **Local storage backend** — files stored on disk (default, zero config)
- **S3 storage backend** — files stored in AWS S3 or compatible (MinIO, R2)
  - Uses the existing `s3` optional dependency (`boto3>=1.34.0`)
- **File serving** — auto-generated download endpoints (`GET /api/{collection}/{id}/files/{field}`)
- **Image processing** — optional thumbnail generation for image uploads

**Existing Infrastructure:**
- `s3` optional dependency already declared in `pyproject.toml`
- Field base class in `src/cinder/collections/schema.py` ready for new field types

**Files to Create/Modify:**
- Create: `src/cinder/storage/` — storage backends (local, s3)
- Create: `src/cinder/collections/fields/file.py` — FileField type
- Modify: `src/cinder/collections/router.py` — file upload/download routes
- Modify: `src/cinder/app.py` — storage backend configuration

---

## Phase 5: Email & Notifications

**Goal:** Real email delivery for transactional emails (password resets, verification, custom).

**Key Features:**

- **Email backend** — async SMTP via `aiosmtplib`
  - Configurable: SMTP host, port, credentials, TLS
  - Environment variable configuration (`CINDER_SMTP_HOST`, etc.)
- **Email verification flow** — send verification email on register, `is_verified` enforcement
- **Password reset emails** — replace console-logged tokens with actual emails
  - Currently, `src/cinder/auth/routes.py` logs reset tokens to console
- **Template system** — simple HTML email templates (Jinja2 or string templates)
- **Custom emails** — `app.send_email(to, subject, body)` API for developer use
- **Rate limiting** — prevent email abuse on forgot-password endpoint

**Existing Infrastructure:**
- `email` optional dependency already declared in `pyproject.toml` (`aiosmtplib>=3.0.0`)
- `_users` table already has `is_verified` column (defaults to 0)
- `_password_resets` table already exists with token + expiry
- Forgot-password route already generates tokens, just logs them instead of emailing

**Files to Create/Modify:**
- Create: `src/cinder/email/` — email backend, templates
- Modify: `src/cinder/auth/routes.py` — send real emails in forgot-password and register
- Modify: `src/cinder/app.py` — email configuration
- Modify: `src/cinder/auth/__init__.py` — email settings on Auth class

---

## Phase 6: Realtime ( Done)

**Goal:** WebSocket-based live updates when collection data changes.

**Key Features:**

- **WebSocket subscriptions** — clients subscribe to collection changes
  - `ws://host/api/realtime` — single WebSocket endpoint
  - Subscribe to specific collections: `{"action": "subscribe", "collection": "posts"}`
  - Receive events: `{"event": "create", "collection": "posts", "record": {...}}`
- **Event types:** `create`, `update`, `delete`
- **Auth-aware** — only receive events for records the user has permission to read
- **Filtering** — subscribe with filters to only receive matching events
- **Connection management** — heartbeat, reconnection, connection limits

**Existing Infrastructure:**
- Starlette has built-in WebSocket support
- Auth middleware already resolves users from JWT tokens
- Collection router already has the CRUD operations that would emit events

**Files to Create/Modify:**
- Create: `src/cinder/realtime/` — WebSocket handler, event bus, subscription manager
- Modify: `src/cinder/collections/store.py` — emit events after CRUD operations
- Modify: `src/cinder/app.py` — mount WebSocket route, configure realtime

---

## Phase 6.5: Realtime — Deferred Enhancements

These items were intentionally deferred from the initial Phase 6 (Realtime) implementation.

- ✅ **Multi-process / multi-node fan-out via Redis pub/sub** — implemented in Phase 8 as `src/cinder/realtime/redis_broker.py`. Activated via `CINDER_REALTIME_BROKER=redis` or `app.configure_redis(url=...)`. The `BrokerProtocol` in `broker.py` is now a formal `typing.Protocol` so custom brokers are type-checkable.
- **Per-record subscription filters with first-class query syntax** — e.g. "subscribe to posts where category=tech". Can already be done today via custom filter callables passed to `broker.subscribe(...)`, but there is no declarative query DSL on the wire protocol yet.
- **Subscription resumption / replay** — event log + `Last-Event-ID` support for SSE so a reconnecting client can catch up on missed events. Requires a persistent event store.
- **WebSocket compression and custom subprotocols** — Phase 6 uses Starlette defaults only. Add `permessage-deflate` and let developers register subprotocols for binary or schema-validated payloads.
- **Realtime metrics & introspection** — expose subscriber counts, dropped-message counters, and per-channel throughput via a `GET /api/realtime/stats` admin endpoint.


---

## Phase 7: Redis & Caching ( Done)

**Goal:** Performance layer with Redis-backed caching, sessions, and rate limiting.

**Key Features:**

- ✅ **Response caching** — cache-aside middleware for GET endpoints with configurable TTL, per-user segmentation, and tag-based invalidation (`src/cinder/cache/`)
- ✅ **Cache invalidation** — automatic invalidation on write via hooks (`src/cinder/cache/invalidation.py`)
- ✅ **Rate limiting** — token-bucket (Redis) / sliding-window (memory) middleware with per-route rules, 429 + `Retry-After` responses (`src/cinder/ratelimit/`)
- ✅ **Pub/Sub** — Redis pub/sub as alternative event bus for realtime (`src/cinder/realtime/redis_broker.py`)
- ✅ **Pluggable backends** — `CacheBackend` and `RateLimitBackend` ABCs let developers supply custom implementations
- ✅ **Zero-config fallback** — in-memory backends used automatically when `CINDER_REDIS_URL` is not set; no Redis required for local dev
- **Session store** — Redis-backed sessions as alternative to stateless JWT (deferred; JWT is still the default)

**Configuration:**
```python
app = Cinder("app.db")
app.configure_redis(url="redis://localhost:6379/0")  # enables everything

# Or fine-grained:
app.cache.use(RedisCacheBackend()).configure(default_ttl=600).exclude("/api/public/feed")
app.rate_limit.rule("/api/posts", limit=50, window=60, scope="user")
```

**Environment variables:**
| Variable | Default | Purpose |
|---|---|---|
| `CINDER_REDIS_URL` | unset | Redis connection string |
| `CINDER_CACHE_ENABLED` | auto | `true`/`false` |
| `CINDER_CACHE_TTL` | `300` | Default TTL in seconds |
| `CINDER_CACHE_PREFIX` | `cinder` | Redis key namespace |
| `CINDER_RATE_LIMIT_ENABLED` | `true` | Master switch |
| `CINDER_RATE_LIMIT_ANON` | `100/60` | Anonymous limit/window |
| `CINDER_RATE_LIMIT_USER` | `1000/60` | Authenticated limit/window |
| `CINDER_REALTIME_BROKER` | `memory` | `memory` \| `redis` |

**Infrastructure:**
- `redis` optional dependency (`redis>=5.0.0`) declared in `pyproject.toml`
- Middleware stack in `src/cinder/pipeline.py` extended with `cache_middleware` and `ratelimit_middleware` slots

---

## Implementation Order

The recommended order is:

```
Phase 3 (Hooks) → Phase 5 (Email) → Phase 4 (Files) → Phase 6 (Realtime) → Phase 8 (Redis)
```

**Rationale:**
- Hooks are foundational — email and file features depend on them (e.g., `after_create` to send welcome email)
- Email before files — email is simpler and unblocks user verification
- Realtime before Redis — basic realtime works in-process; Redis adds multi-process support
