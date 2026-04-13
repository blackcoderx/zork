---
title: "Fly.io"
description: "Deploy your Cinder app to Fly.io"
sidebar:
  order: 5
---

[Fly.io](https://fly.io) runs your app as a Docker container distributed across global regions. It's a good choice for low-latency APIs and apps that need to run close to users.

---

## Prerequisites

Install the Fly CLI and log in:

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Log in
fly auth login
```

---

## Generate the files

```bash
cinderapi deploy --platform fly --app main.py
```

This creates:

- `fly.toml` — app configuration
- `Dockerfile` — container build instructions
- `.dockerignore` — excludes unnecessary files from the build
- `cinder.toml` — deployment record

---

## `fly.toml`

```toml
app = "myapp"
primary_region = "iad"

[build]

[deploy]
  release_command = "cinderapi migrate run --app main.py"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 1

  [http_service.concurrency]
    type = "connections"
    hard_limit = 250
    soft_limit = 200

[[http_service.checks]]
  grace_period = "10s"
  interval = "15s"
  method = "GET"
  path = "/api/health"
  timeout = "2s"

[[vm]]
  memory = "512mb"
  cpu_kind = "shared"
  cpus = 1
```

Key settings:

- `release_command` — runs `cinderapi migrate run` before each deploy, in a temporary VM, before traffic switches over. Migrations are applied safely with zero downtime.
- `force_https = true` — all HTTP traffic is redirected to HTTPS automatically
- `auto_stop_machines` / `auto_start_machines` — machines stop when idle and start on incoming requests (saves cost on low-traffic apps)
- Health checks on `/api/health` ensure traffic only goes to healthy instances

---

## Deploy

**1. Create the Fly app (without deploying yet):**

```bash
fly launch --no-deploy
```

This registers the app name and region without deploying anything.

**2. Set your secret key:**

```bash
fly secrets set CINDER_SECRET=$(cinderapi generate-secret)
```

Secrets are encrypted and injected as environment variables at runtime. They are never stored in `fly.toml`.

**3. Create a Postgres database** (if your app uses it):

```bash
fly postgres create --name myapp-db
fly postgres attach myapp-db
```

`fly postgres attach` automatically sets `DATABASE_URL` in your app's environment.

**4. Create Redis** (if your app uses it):

```bash
fly redis create
```

Copy the connection URL from the output and set it:

```bash
fly secrets set CINDER_REDIS_URL=redis://...
```

**5. Deploy:**

```bash
fly deploy
```

Fly builds the Docker image, runs migrations via the release command, then switches traffic to the new version.

---

## Health checks

Fly checks `GET /api/health` every 15 seconds. Instances that fail the check are restarted and removed from the load balancer. Cinder exposes `/api/health` automatically.

---

## Scaling

Scale horizontally by adding machines:

```bash
fly scale count 3
```

Scale vertically by changing the VM size:

```bash
fly scale vm shared-cpu-2x
```

---

## Logs and monitoring

```bash
# Stream live logs
fly logs

# SSH into a running machine
fly ssh console

# Check machine status
fly status
```

---

## Regions

Change `primary_region` in `fly.toml` to deploy closer to your users. Use `fly platform regions` to list available regions.

To run in multiple regions:

```bash
fly regions add lhr sin
fly scale count 3
```

Fly automatically routes requests to the nearest healthy machine.
