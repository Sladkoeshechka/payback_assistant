# Deploy (stage 11)

## Step 1 — app + PostgreSQL (current)

No Caddy yet. The app is reachable on the host at port 8000; Telegram still uses long polling.

### Prerequisites

- Docker and Docker Compose plugin
- A filled `.env` (copy from `.env.example`). For a first smoke test, `DEV_MODE=true` lets the bot start even if PlanFix schema validation fails.

### Run

```bash
docker compose up --build -d
curl http://127.0.0.1:8000/health
docker compose logs -f app
```

Or: `make docker-up` / `make docker-logs` / `make docker-down`.

Compose overrides `DATABASE_URL` to Postgres (`payback:payback@db:5432/payback`). Local `make run` can keep using SQLite.

### What starts

| Service | Role |
|---------|------|
| `db` | PostgreSQL 16; data in volume `pgdata` |
| `app` | migrations (`alembic upgrade head`), then FastAPI + bot polling |

### Stop

```bash
docker compose down          # keep database volume
docker compose down -v       # also wipe Postgres data
```

## Step 2 — Caddy / HTTPS (next)

Public HTTPS for PlanFix webhooks. Not in this compose file yet.
