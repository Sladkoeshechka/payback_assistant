.DEFAULT_GOAL := help
.PHONY: help sync install lint format typecheck test check run show-db reset-db \
	docker-up docker-down docker-logs docker-build

help:
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | expand -t20

sync: ## Create .venv and install project + dev deps (uv)
	uv sync

install: sync ## Alias for sync (uv-managed env)

lint: ## Check formatting and lint rules
	uv run ruff format --check .
	uv run ruff check .

format: ## Apply formatting and safe lint fixes
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Run mypy
	uv run mypy payback tests

test: ## Run the test suite
	uv run pytest

check: lint typecheck test ## Everything CI would run

run: ## Start the service
	uv run python -m payback

show-db: ## Print users, invites, and expenses from DATABASE_URL
	uv run python scripts/show_db.py

reset-db: ## Wipe and recreate all tables (requires confirmation flag)
	uv run python scripts/reset_db.py --yes

docker-build: ## Build the app image
	docker compose build

docker-up: ## Start app + Postgres + Caddy (DOMAIN in env file; optional PAYBACK_ENV_FILE)
	docker compose up --build -d

docker-down: ## Stop compose services
	docker compose down

docker-logs: ## Follow app container logs
	docker compose logs -f app
