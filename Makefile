# UrjaSetu developer commands (docs/09_PHASE_0_SETUP.md Step 11).
# Every team member uses these so behaviour is identical across machines.

SHELL := /bin/bash
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
# Override when your user is not in the `docker` group:
#     make up COMPOSE="sudo docker compose"
COMPOSE ?= docker compose

.DEFAULT_GOAL := help
.PHONY: bootstrap demo test-chain test-web
.PHONY: help venv install up down logs wait-db migrate revision downgrade dev test lint format typecheck check clean verify

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

venv: ## Create the local virtual environment
	@test -d $(VENV) || python3.12 -m venv $(VENV)

install: venv ## Install runtime and development dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

up: ## Start PostgreSQL and wait until it accepts connections
	$(COMPOSE) up -d db
	@$(MAKE) --no-print-directory wait-db

down: ## Stop PostgreSQL (data volume is preserved)
	$(COMPOSE) down

logs: ## Tail PostgreSQL logs
	$(COMPOSE) logs -f db

wait-db: ## Block until the database healthcheck reports healthy
	@echo "Waiting for PostgreSQL..."
	@for i in $$(seq 1 40); do \
		status=$$($(COMPOSE) ps --format json db 2>/dev/null | grep -o '"Health":"[a-z]*"' | head -1 | cut -d'"' -f4); \
		if [ "$$status" = "healthy" ]; then echo "PostgreSQL is healthy."; exit 0; fi; \
		sleep 1; \
	done; \
	echo "PostgreSQL did not become healthy in time." >&2; exit 1

migrate: ## Apply all migrations (alembic upgrade head)
	cd backend && ../$(PY) -m alembic upgrade head

revision: ## Autogenerate a migration: make revision m="message"
	@test -n "$(m)" || (echo 'Usage: make revision m="your message"' >&2; exit 1)
	cd backend && ../$(PY) -m alembic revision --autogenerate -m "$(m)"

downgrade: ## Roll back one migration
	cd backend && ../$(PY) -m alembic downgrade -1

dev: ## Run the API with auto-reload on http://localhost:8000
	$(VENV)/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend

bootstrap: ## Create the fictional Gujarat community (preserves existing data)
	PYTHONPATH=backend $(PY) scripts/bootstrap_workspace.py

demo: ## Start the API, website and persistent local blockchain
	bash scripts/dev_workspace.sh

test-chain: ## Verify Solidity and Python publication against the local EVM
	cd blockchain && npm test
	PYTHONPATH=backend $(PY) scripts/verify_local_chain.py

test-web: ## Typecheck, unit-test and build the connected website
	cd frontend && npm run check && npm test && npm run build

test-browser: ## Real two-user browser journey in a disposable PostgreSQL database
	$(PY) scripts/run_browser_tests.py

test: ## Run the test suite
	$(VENV)/bin/pytest

lint: ## Lint (no changes written)
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .

format: ## Auto-format and fix lint issues
	$(VENV)/bin/ruff format .
	$(VENV)/bin/ruff check --fix .

typecheck: ## Run mypy over backend/app
	$(VENV)/bin/mypy

check: lint typecheck test ## Lint, typecheck and test

verify: up migrate test ## Full Phase 0 gate: database up, migrated, tests green

clean: ## Remove caches and the virtual environment
	rm -rf $(VENV) .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
