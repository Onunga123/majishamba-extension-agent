#!/bin/bash
# Production deployment script for Kachieng AI Agent.
# This script does NOT load demo fixtures or create demo users.
# Production starts empty — officers are provisioned individually.

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

echo ""
echo "==> Production deployment ready."
echo ""
echo "    IMPORTANT: No demo fixtures or demo users are loaded in production."
echo "    Production starts EMPTY. To set up:"
echo ""
echo "    1. Create your first officer account:"
echo "       .venv/bin/python manage.py create_officer --username <username> --full-name '<name>' --role extension_officer"
echo "       .venv/bin/python manage.py changepassword <username>"
echo ""
echo "    2. Seed locality clusters (14 Kachieng localities, no households/plots):"
echo "       .venv/bin/python manage.py seed_kachieng_clusters"
echo ""
echo "    3. Geocode locality coordinates (needs internet):"
echo "       .venv/bin/python manage.py geocode_kachieng_localities"
echo "       .venv/bin/python manage.py geocode_kachieng_localities --approve KACH-01"
echo ""
echo "    4. Refresh weather from Open-Meteo (needs internet):"
echo "       .venv/bin/python manage.py refresh_weather"
echo ""
echo "    5. Start gunicorn:"
echo "       DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 120"
echo ""
echo "    6. Start an RQ worker for background jobs:"
echo "       DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/python manage.py rqworker default &"
echo ""
echo "    7. Configure nginx to proxy_pass to http://127.0.0.1:8000 with HTTPS."
