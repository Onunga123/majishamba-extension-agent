# Production deployment — Kachieng AI Agent

This guide walks through deploying the Kachieng AI Agent for real extension-officer use
at the Nyatike Sub-County Agricultural Office.

## Prerequisites

- Ubuntu 22.04+ or Debian 12+ server
- Python 3.11+
- PostgreSQL 16 + PostGIS extension
- Valkey 7 (Redis-compatible) or Redis 7
- Ollama 0.3+ with `qwen2.5:7b-instruct` pulled
- nginx (reverse proxy with HTTPS)
- SSL certificate (Let's Encrypt or commercial)

## Quick start (bare metal)

```bash
# 1. Clone
git clone https://github.com/Onunga123/majishamba-extension-agent.git
cd majishamba-extension-agent

# 2. Create .env from template
cp .env.example .env
# Edit .env with production secrets:
#   DJANGO_SETTINGS_MODULE=config.settings.production
#   MAJISHAMBA_SECRET_KEY=<generate with: python -c 'import secrets; print(secrets.token_urlsafe(64))'>
#   MAJISHAMBA_DEBUG=False
#   MAJISHAMBA_ALLOWED_HOSTS=officer.nyatike.example,your-domain.com
#   MAJISHAMBA_DB_NAME=majishamba
#   MAJISHAMBA_DB_USER=majishamba
#   MAJISHAMBA_DB_PASSWORD=<strong password>
#   REDIS_URL=redis://127.0.0.1:6379/0
#   OLLAMA_HOST=http://127.0.0.1:11434
#   OLLAMA_MODEL=qwen2.5:7b-instruct
#   KACHIENG_MAP_API_KEY=<your Stadia Maps API key>
#   DEMO_MODE=0

# 3. Deploy
bash scripts/deploy_production.sh

# 4. Start gunicorn
DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/gunicorn config.wsgi:application \
  --bind 127.0.0.1:8000 --workers 3 --timeout 120

# 5. Start RQ worker (background jobs)
DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/python manage.py rqworker default &

# 6. Configure nginx to proxy_pass to http://127.0.0.1:8000 with HTTPS
```

## Quick start (Docker)

```bash
cp .env.example .env
# Edit .env with production secrets (see above)

docker compose -f docker-compose.prod.yml up -d

# Pull the Ollama model (first time only)
docker compose -f docker-compose.prod.yml exec ollama ollama pull qwen2.5:7b-instruct
```

## Security hardening

The production settings (`config/settings/production.py`) enforce:

- `DEBUG=False` — no stack traces, no debug toolbar
- `SECURE_SSL_REDIRECT=True` — HTTP → HTTPS redirect
- `SECURE_PROXY_SSL_HEADER` — trusts `X-Forwarded-Proto` from nginx
- `SESSION_COOKIE_SECURE=True` — cookies only over HTTPS
- `CSRF_COOKIE_SECURE=True` — CSRF cookie only over HTTPS
- `SECURE_HSTS_SECONDS=2592000` — HSTS for 30 days
- `SECURE_HSTS_INCLUDE_SUBDOMAINS=True`
- `SECURE_HSTS_PRELOAD=True`
- `SECURE_REFERRER_POLICY=same-origin`
- `SECURE_CONTENT_TYPE_NOSNIFF=True`
- `X_FRAME_OPTIONS=DENY` — no iframe embedding
- `DEMO_MODE=False` — no demo account cards on login
- Synthetic test scenarios hidden from dashboard
- Structured JSON logging (no secrets in logs)
- Secret-key required (raises RuntimeError if not set)
- `ALLOWED_HOSTS` from env var

## Data sources in production

- **Weather:** Officer manually reads KMD bulletins on meteo.go.ke, then uses
  `/integrations/kmd/ingest/` to transcribe metadata. No auto-fetch.
- **Pests:** Officer submits field reports via `/integrations/pests/report/`
  or transcribes official notices via `/integrations/pests/notice/`.
- **KALRO:** Bibliographic metadata only. Content extraction is permission-pending.
- **Map:** Stadia Maps with API key (set `KACHIENG_MAP_API_KEY` in `.env`).

## Soft-delete

Advisories are never hard-deleted. Officers can soft-delete via the "Delete…"
button on the advisory detail page. Soft-deleted advisories:
- Disappear from the active advisory list
- Appear in the "Deleted" view (supervisors only)
- Are preserved in the database for audit/compliance
- Can be restored by supervisors
- All soft-delete and restore actions are logged to the audit trail

## Backups

```bash
# Database backup (daily cron)
pg_dump -U majishamba majishamba | gzip > backups/majishamba_$(date +%Y%m%d).sql.gz

# Restore
gunzip -c backups/majishamba_20260101.sql.gz | psql -U majishamba majishamba
```

## Health check

```bash
# Check the app is responding
curl -f http://127.0.0.1:8000/dashboard/ -H "Host: officer.nyatike.example" && echo "OK"
```
