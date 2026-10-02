.DEFAULT_GOAL := help
.PHONY: help venv install lint format typecheck test check run

VENV ?= .venv
PY := $(VENV)/bin/python

help:
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | expand -t20

venv: ## Create the virtualenv
	python3 -m venv $(abspath $(VENV))

install: ## Install the project with its dev dependencies
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"

lint: ## Check formatting and lint rules
	$(PY) -m ruff format --check .
	$(PY) -m ruff check .

format: ## Apply formatting and safe lint fixes
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

typecheck: ## Run mypy
	$(PY) -m mypy payback tests

test: ## Run the test suite
	$(PY) -m pytest

check: lint typecheck test ## Everything CI would run

run: ## Start the service
	$(PY) -m payback
