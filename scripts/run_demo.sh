#!/usr/bin/env bash
# scripts/run_demo.sh — one-shot demo: install deps, migrate, load fixtures,
# pull Ollama model, start the Django dev server.
# Equivalent to `make demo` but bash-only.
set -euo pipefail

PYTHON=${PYTHON:-python3.11}
VENV=${VENV:-.venv}

echo "==> Creating venv"
[ -d "$VENV" ] || "$PYTHON" -m venv "$VENV"

echo "==> Installing deps"
"$VENV/bin/pip" install --upgrade pip --quiet
"$VENV/bin/pip" install -e ".[dev]" --quiet

echo "==> Migrate"
"$VENV/bin/python" manage.py migrate --noinput

echo "==> Load fixtures + seed 14 Kachieng clusters"
"$VENV/bin/python" manage.py loaddata \
  data/fixtures/migori_kachieng_clusters.json \
  data/fixtures/migori_kachieng_plots.json \
  data/fixtures/migori_crop_calendars.json \
  data/fixtures/nyatike_weather_signals.json \
  data/fixtures/migori_pest_alerts.json \
  data/fixtures/migori_market_prices.json \
  --ignorenonexistent || true
"$VENV/bin/python" manage.py seed_kachieng_clusters || true
"$VENV/bin/python" scripts/load_demo_data.py || true
echo "==> (No synthetic demo accounts are seeded. To create a real officer for testing, run:"
echo "       python manage.py create_officer --username jdoe --full-name 'John Doe' --role extension_officer)"
echo "       python manage.py changepassword jdoe)"

echo "==> Ollama (optional)"
bash scripts/setup_ollama.sh || true

PORT=${PORT:-8000}
echo "==> Start Django dev server on http://127.0.0.1:$PORT"
"$VENV/bin/python" manage.py runserver "127.0.0.1:$PORT"
