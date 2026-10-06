# System architecture — Kachieng AI Agent

This document expands on `ARCHITECTURE.md` (the one-page summary at the repo root). Read `ARCHITECTURE.md` first; this file adds deployment and code-organisation detail.

## High-level diagram

```text
┌─────────────────────────────────────────────────────────────────────┐
│  Officer browser (Django templates + HTMX + MapLibre GL JS)         │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ HTTPS (production)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Django 5 (apps/) — custom user, ORM, admin, HTMX, audit middleware │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  apps/dashboard       (officer dashboard, map, audit)        │    │
│  │  apps/advisories      (request + list + detail + edit)     │    │
│  │  apps/approvals       (the gate)                            │    │
│  │  apps/tasks           (approval-gated create)               │    │
│  │  apps/agents          (LangGraph graph + runner + schemas)   │    │
│  │  apps/mcp_tools       (custom MCP server — 8 tools)         │    │
│  │  apps/audit           (audit event log + middleware)        │    │
│  │  apps/accounts        (custom user, roles, permissions)     │    │
│  │  apps/geography, clusters, plots,                          │    │
│  │  apps/calendars, weather, pests, markets  (domain models)  │    │
│  └─────────────────────────────────────────────────────────────┘    │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ in-process (same Python process)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LangGraph agent (apps/agents/graph.py) — 11 nodes                   │
│  Nodes call MCP tools in apps/mcp_tools/tools.py                    │
└─────────────┬───────────────────────────────────┬───────────────────┘
              │                                   │
              ▼                                   ▼
┌──────────────────────────────┐     ┌────────────────────────────────┐
│  Ollama qwen2.5:7b-instruct  │     │  Pydantic schemas              │
│  (host: OLLAMA_HOST)         │     │  (AdvisoryDraft, tool inputs)  │
└──────────────────────────────┘     └────────────────────────────────┘
              │
              ▼ on failure
┌──────────────────────────────┐
│  Deterministic fallback      │
│  template generator          │
└──────────────────────────────┘
```

## External MCP clients

The custom MCP server can also be invoked from external MCP clients (Claude Desktop, a partner agent, a test harness) over stdio via `apps/mcp_tools/server.py` using FastMCP. The same `TOOL_REGISTRY` functions are used, so behaviour is identical to in-process calls.

## Borrowed MCP server (filesystem)

Used only in development, restricted to `docs/calendars/`. Configured via `MAJISHAMBA_BORROWED_FILESYSTEM_MCP_ROOT` in `config/settings/base.py`. Not exposed in production.

## Datastores

| Component | Demo | Production |
|---|---|---|
| Database | SQLite (`db.sqlite3`) | PostgreSQL + PostGIS |
| Cache / queue | Local-memory | Valkey (Redis-compatible) |
| Background jobs | Django-RQ inline | Django-RQ + Valkey worker |
| Model | Ollama local | Ollama local (same; can be shared by multiple officers) |

## Logging

Structured JSON logging via `python-json-logger`. Audit events are stored in `AuditEvent` rows AND logged via the `majishamba.audit` logger. Secrets are stripped by `_sanitize_inputs` and `_summarise` before any text reaches the log.

## Background jobs

In the demo, Django-RQ runs `ASYNC=False` (inline) so no separate worker process is needed. In production, a Valkey-backed RQ worker handles agent runs and any future scheduled re-evidence tasks.

## Deployment

The demo runs on SQLite with the local Django dev server. A production deployment would use:

- gunicorn / uvicorn behind nginx
- PostgreSQL 16 + PostGIS
- Valkey 7
- Ollama 0.3+ on the same host or a LAN host
- `config.settings.production` with `MAJISHAMBA_SECRET_KEY`, `REDIS_URL`, `MAJISHAMBA_DB_*` env vars
- HTTPS enforced; HSTS on; CSRF_COOKIE_SECURE; SESSION_COOKIE_SECURE

The repo does not include a Docker Compose file by design — the Makefile is the source of truth and works without Docker. Operators who want Docker can wrap the Makefile targets.

## What's deliberately simple

- GIS: the demo uses `FloatField` for centroid lat/lon, not `PointField`, so PostGIS is optional. The `Ward.centroid_lat`/`centroid_lon` fields keep the demo trivial while leaving room for GeoDjango in production.
- Tailwind: CDN for the demo. A production build would compile Tailwind via `django-tailwind` (already in deps).
- HTMX: minimal — only used for the dashboard's audit-event tail and the request-advisory spinner.
- MapLibre GL JS: free OSM raster tiles (no API key). A production deployment would use a hosted tile provider or self-hosted tiles.

## What's deliberately strict

- Pydantic validation on every MCP tool input (`apps/agents/schemas.py`).
- Pydantic validation on the model's JSON output (`AdvisoryDraft`).
- Server-side permission checks on every mutating view (`apps/accounts/permissions.py`).
- Approval gate enforced in `apps/tasks/service.py` — the action tool cannot bypass it.
- Audit log written for every tool call, every HTTP mutation, every agent run start/end, every approval.
