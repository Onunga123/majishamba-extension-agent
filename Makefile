# MajiShamba Extension Agent — Makefile
# Goal: a stranger can run `git clone ... && cd majishamba && make demo` and see a working system.
# The demo runs on SQLite by default so it works without PostgreSQL / PostGIS.
# Ollama is started if available; otherwise the deterministic fallback kicks in.

SHELL := /bin/bash
.DEFAULT_GOAL := help
PYTHON ?= python3.11
VENV ?= .venv
BIN := $(VENV)/bin
PORT ?= 8000

# Toggle GIS/Postgres for local pilots. Demo runs without them.
USE_POSTGIS ?= 0
USE_POSTGRES ?= 0

.PHONY: help demo setup install db fixtures ollama run test lint typecheck security clean reset-demo

help: ## Show this help
        @grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

demo: setup db fixtures ollama run ## One-command demo: install deps, load Kachieng fixtures, start Ollama, run server

setup: install ## Install Python deps into local venv
        @echo "==> Verifying Python & Django"
        @$(BIN)/python -c "import django; print('Django', django.get_version())"

install: ## Create venv and install dependencies
        @echo "==> Creating venv at $(VENV)"
        @command -v $(PYTHON) >/dev/null 2>&1 || { echo "ERROR: $(PYTHON) not found. Install Python 3.11+."; exit 1; }
        @[ -d $(VENV) ] || $(PYTHON) -m venv $(VENV)
        @echo "==> Installing dependencies"
        @$(BIN)/pip install --upgrade pip --quiet
        @$(BIN)/pip install -e ".[dev]" --quiet || { echo "pip install failed; check pyproject.toml"; exit 1; }
        @$(BIN)/python -c "import django, langgraph, mcp, pydantic; print('Core deps OK')"

db: ## Run migrations
        @echo "==> Applying migrations"
        @$(BIN)/python manage.py migrate --noinput

fixtures: ## Load synthetic Kachieng fixtures + seed 14 clusters
        @echo "==> Loading synthetic fixtures (clusters, plots, calendars, weather, pests, markets)"
        @$(BIN)/python manage.py loaddata \
                data/fixtures/migori_kachieng_clusters.json \
                data/fixtures/migori_kachieng_plots.json \
                data/fixtures/migori_crop_calendars.json \
                data/fixtures/nyatike_weather_signals.json \
                data/fixtures/migori_pest_alerts.json \
                data/fixtures/migori_market_prices.json \
                --ignorenonexistent || true
        @echo "==> Seeding 14 Kachieng pilot clusters (idempotent; preserves KACH-01..KACH-03 data)"
        @$(BIN)/python manage.py seed_kachieng_clusters || true
        @echo "==> (Synthetic demo accounts are no longer seeded. Use 'python manage.py create_officer' for real accounts.)"
        @$(BIN)/python scripts/load_demo_data.py || true

ollama: ## Pull Qwen2.5-7B-Instruct if Ollama is installed; otherwise mark degraded mode
        @echo "==> Checking Ollama availability"
        @if command -v ollama >/dev/null 2>&1; then \
                echo "Ollama found. Ensuring service is running..."; \
                ollama serve >/tmp/ollama.log 2>&1 & sleep 2 || true; \
                echo "Pulling qwen2.5:7b-instruct (first run may take several minutes)..."; \
                ollama pull qwen2.5:7b-instruct || echo "WARN: pull failed; system will use deterministic fallback"; \
        else \
                echo "WARN: Ollama not installed. System will run in DEGRADED mode using deterministic template."; \
                echo "      Install Ollama from https://ollama.com to enable the open-weights model run."; \
        fi

run: ## Start Django dev server
        @echo "==> Starting Django dev server on http://127.0.0.1:$(PORT)"
        @$(BIN)/python manage.py runserver 127.0.0.1:$(PORT)

test: ## Run pytest suite
        @$(BIN)/python -m pytest -q

lint: ## Run Ruff + Black --check
        @$(BIN)/ruff check . || true
        @$(BIN)/black --check . || true

typecheck: ## Run mypy
        @$(BIN)/mypy apps config || true

security: ## Run pip-audit + Semgrep CE + Gitleaks
        @echo "==> pip-audit"
        @$(BIN)/pip-audit || true
        @echo "==> Semgrep CE (configs only)"
        @$(BIN)/semgrep --config auto --error apps config || true
        @echo "==> Gitleaks"
        @if command -v gitleaks >/dev/null 2>&1; then gitleaks detect --source . --no-banner || true; \
        else echo "gitleaks not installed, skipping"; fi

clean: ## Remove caches, venv, sqlite db
        rm -rf .venv .pytest_cache .ruff_cache .mypy_cache **/__pycache__ db.sqlite3
        find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

reset-demo: clean db fixtures ## Reset the demo DB and re-load fixtures
        @echo "==> Demo environment reset."
