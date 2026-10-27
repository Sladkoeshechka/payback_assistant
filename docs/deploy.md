# Deploy (stage 11)

PlanFix GUI steps: [planfix_setup/setup.md](planfix_setup/setup.md).

Stack: **app** (bot + FastAPI) + **PostgreSQL** + **Caddy** (HTTPS).

## Prerequisites

- Docker and Docker Compose plugin
- Env file with bot/PlanFix secrets (see `.env.example`)
- Public DNS name pointing at the VPS (e.g. DuckDNS) for real certificates
- Ports **80** and **443** open on the host

Prefer keeping secrets **outside** the git workspace:

```bash
mkdir -p ~/.config/payback
cp .env.example ~/.config/payback/env
# edit ~/.config/payback/env — fill BOT_TOKEN, PlanFix, WEBHOOK_SECRET, DOMAIN, …
```

For a first smoke test, `DEV_MODE=true` lets the bot start even if PlanFix schema validation fails.

## Run

```bash
# optional if the env file is not ./.env
export PAYBACK_ENV_FILE=$HOME/.config/payback/env

docker compose up --build -d

curl -fsS "https://yourbot.duckdns.org/health"   # same value as DOMAIN in the env file
docker compose logs -f app caddy
```

Or: `make docker-up` (set `PAYBACK_ENV_FILE` only if secrets are not in `./.env`).

Compose app uses Postgres on the internal host `db` (`payback:payback@db:5432/payback`).  
Postgres publishes `localhost:5432` for local `make run` / `make test`.

**Local development (prod-like):**

```bash
make db-up                          # Postgres + payback_test database
# DATABASE_URL=postgresql+asyncpg://payback:payback@127.0.0.1:5432/payback
make run
make test                           # uses payback_test
make test-sqlite                    # optional fast fallback (no Docker DB)
```

SQLite remains a documented fallback (`DATABASE_URL=sqlite+aiosqlite:///./payback.db`);  
feature parity with prod (e.g. `SKIP LOCKED`) is not guaranteed there.

## What starts

| Service | Role |
|---------|------|
| `db` | PostgreSQL 16; data in volume `pgdata` |
| `app` | `alembic upgrade head`, then FastAPI + Telegram polling (port 8000 internal only) |
| `caddy` | HTTPS on 80/443 → `app:8000`; Let's Encrypt when `DOMAIN` is public |

## PlanFix webhook

```text
POST https://<DOMAIN>/webhooks/planfix
```

Body includes `secret` = `WEBHOOK_SECRET` (see spec §7).

## Stop

```bash
docker compose down          # keep database + Caddy cert volumes
docker compose down -v       # wipe Postgres and cert data
```

## Notes

- App is **not** published as host `:8000` anymore; use `https://$DOMAIN/health`.
- First certificate issuance needs DNS already pointing at this machine.
- Telegram can stay on **long polling**; Caddy is required for **PlanFix → you** webhooks.
