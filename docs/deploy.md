# Deploy (stage 11)

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

Compose overrides `DATABASE_URL` to Postgres (`payback:payback@db:5432/payback`).  
Local `make run` can keep using SQLite without Caddy.

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
