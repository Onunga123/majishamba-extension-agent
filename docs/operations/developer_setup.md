# Developer setup — Kachieng AI Agent

## Prerequisites

- **Python 3.11+** (3.12 also tested).
- **make** (any flavour).
- **Optional but recommended:** Ollama 0.3+ for the open-weights model run.
- **Optional for production:** PostgreSQL 16 + PostGIS, Valkey 7.

The demo runs on SQLite and local-memory cache so it works without PostgreSQL/PostGIS/Valkey/Ollama.

## One-command demo

```bash
git clone <your-repo-url> majishamba
cd majishamba
make demo
```

Open http://127.0.0.1:8000/accounts/login/ and sign in with a real officer
account. To create one:

```bash
.venv/bin/python manage.py create_officer --username jdoe --full-name "John Doe" --role extension_officer
.venv/bin/python manage.py changepassword jdoe
```

## Step-by-step (if `make demo` fails)

```bash
make install           # create .venv and install deps
make db                # apply migrations (SQLite)
make fixtures          # load synthetic Kachieng fixtures + seed 14 clusters
make ollama            # pull qwen2.5:7b-instruct if Ollama is installed
make run               # start Django dev server
```

The setup scripts no longer seed any synthetic demo accounts. Use
`python manage.py create_officer` to create a real account for testing
(see above). To clean up leftover synthetic demo accounts from an older
deploy, run `python manage.py cleanup_demo_accounts --dry-run`.

## Running tests

```bash
make test       # pytest
make lint       # ruff + black --check
make typecheck  # mypy
make security   # pip-audit + semgrep + (gitleaks if installed)
```

## Running the standalone MCP server

The custom MCP server is exposed over stdio via FastMCP. To run it:

```bash
.venv/bin/python -m apps.mcp_tools.server
```

It speaks the official MCP protocol. You can test it from a Python MCP client:

```python
from mcp import Client
client = Client(stdio_server=["python", "-m", "apps.mcp_tools.server"])
tools = await client.list_tools()
res = await client.call("get_cluster_plot_history", {"cluster_id": "KACH-01"})
```

## Borrowed MCP server (filesystem)

To use the official filesystem MCP server for development:

```bash
npx -y @modelcontextprotocol/server-filesystem /home/z/my-project/majishamba/docs/calendars
```

(Install Node.js separately; it is not a Python dep.) The agent does not depend on this server for the demo.

## Resetting the demo DB

```bash
make reset-demo
```

This removes `db.sqlite3`, re-applies migrations, and reloads fixtures.

## Switching to PostgreSQL + PostGIS

Set env vars and re-run:

```bash
export USE_POSTGRES=1
export USE_POSTGIS=1
export MAJISHAMBA_DB_NAME=majishamba
export MAJISHAMBA_DB_USER=majishamba
export MAJISHAMBA_DB_PASSWORD=majishamba
make reset-demo
```

The settings module (`config/settings/base.py`) automatically switches to PostGIS when `USE_POSTGIS=1`.

## Switching to Valkey (Redis-compatible)

In production, set `REDIS_URL`:

```bash
export REDIS_URL=redis://127.0.0.1:6379/0
```

In demo mode, Django-RQ runs inline (`ASYNC=False`) so no worker is needed.

## Production settings

Use `config.settings.production`:

```bash
export DJANGO_SETTINGS_MODULE=config.settings.production
export MAJISHAMBA_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(64))')
export MAJISHAMBA_ALLOWED_HOSTS=officer.nyatike.example
gunicorn config.wsgi:application -b 127.0.0.1:8000
```

## Project scripts

| Script | Purpose |
|---|---|
| `scripts/setup_ollama.sh` | Pull `qwen2.5:7b-instruct` via Ollama |
| `scripts/load_demo_data.py` | Seed demo officer/supervisor/viewer |
| `scripts/run_demo.sh` | Bash equivalent of `make demo` |
| `scripts/smoke_test.py` | End-to-end smoke test (agent + approval + task) |
| `scripts/test_mcp_server.py` | Verify the MCP server has 8 tools registered |

## Troubleshooting

- **`pip install` fails on classifier `Topic :: Scientific/Engineering :: Agriculture`.** Use the version in `pyproject.toml` (we use `Topic :: Scientific/Engineering` without the subtopic, since PyPI doesn't accept `Agriculture` as a classifier).
- **`loaddata` fails on UNIQUE constraint for crop calendars.** The fixture has two entries with the same `crop/zone_label/season` — make sure the third entry has `zone_label="Migori-Low-Mid-Stale"` (which it does in the current fixtures).
- **Ollama not installed.** The agent logs `WARN: Ollama not installed` and falls back to the deterministic template. The demo still works.
- **MapLibre map is blank.** You need internet access to load the OSM raster tiles. The map is non-essential to the demo flow.
- **Tests fail with `Missing staticfiles manifest entry for 'css/app.css'`.** Make sure `STATICFILES_STORAGE` is `django.contrib.staticfiles.storage.StaticFilesStorage` (set in `config/settings/development.py`).
