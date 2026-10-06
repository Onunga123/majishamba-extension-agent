#!/bin/bash
# Production deployment script for Kachieng AI Agent.
# Run on a clean Ubuntu/Debian host with Python 3.11+, PostgreSQL, and Ollama installed.
#
# Prerequisites:
#   - PostgreSQL 16 + PostGIS extension
#   - Valkey 7 (or Redis 7)
#   - Ollama 0.3+ with qwen2.5:7b-instruct pulled
#   - nginx (reverse proxy with HTTPS)
#   - A .env file with MAJISHAMBA_SECRET_KEY, DB credentials, REDIS_URL, etc.
#
# Usage:
#   cp .env.example .env  # edit with production secrets
#   bash scripts/deploy_production.sh

set -euo pipefail

echo "==> Kachieng AI Agent — Production Deployment"
echo ""

# Check .env exists
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Copy .env.example to .env and edit with production secrets."
    exit 1
fi

export $(grep -v '^#' .env | xargs)

# Check SECRET_KEY
if [ -z "${MAJISHAMBA_SECRET_KEY:-}" ]; then
    echo "ERROR: MAJISHAMBA_SECRET_KEY must be set in .env"
    exit 1
fi

echo "==> Installing Python dependencies"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -e "." --quiet
.venv/bin/pip install gunicorn --quiet

echo "==> Collecting static files"
.venv/bin/python manage.py collectstatic --noinput

echo "==> Applying migrations"
.venv/bin/python manage.py migrate --noinput

echo "==> Loading fixtures + seeding 14 clusters"
.venv/bin/python manage.py loaddata data/fixtures/*.json --ignorenonexistent || true
.venv/bin/python manage.py seed_kachieng_clusters
.venv/bin/python scripts/load_demo_data.py

echo ""
echo "==> Production deployment ready."
echo "    Start gunicorn:"
echo "    DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 120"
echo ""
echo "    Configure nginx to proxy_pass to http://127.0.0.1:8000 with HTTPS."
echo "    Start an RQ worker for background jobs:"
echo "    DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/python manage.py rqworker default"
