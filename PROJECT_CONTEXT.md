# Project Context — MajiShamba Extension Agent

This orients a new contributor (human or agent) to the repository in one read.
It is deliberately short; deeper detail lives under `docs/`.

## What this is

MajiShamba is a server-rendered Django extension-agent platform for the
Nyatike Sub-County Agricultural Office (Kachieng ward, Migori County, Kenya).
An **extension officer** requests a draft agronomic advisory for a farmer
cluster; a **supervisor/approver** reviews and approves it before any action
is taken. The advisory lifecycle is `DRAFT → APPROVED / REJECTED / DEFERRED /
NEEDS_EVIDENCE`. No advisory reaches a farmer without a human approval.

## Stack

Django 5.x (custom `accounts.User`), HTMX for partials, django-rq for
background jobs (local-memory queue in dev), LangGraph + MCP for the advisory
pipeline, Ollama / OpenRouter for open-weights model inference with a
deterministic template fallback. SQLite in dev, PostgreSQL/PostGIS optional.
Tailwind for styling. Tests run under pytest + pytest-django.

## Repository layout

```
apps/          domain apps: accounts, geography, clusters, plots, calendars,
               weather, pests, markets, advisories, approvals, tasks, audit,
               agents, mcp_tools, integrations, dashboard, api (new)
config/        settings (base/development/production), urls, handlers
docs/          architecture, product, governance, operations, implementation (new)
tests/         integration/, security/, factories/
templates/     server-rendered HTML
static/        css (design tokens), js, images
```

## Key domain rules

- **Roles:** `EXTENSION_OFFICER`, `SUPERVISOR`, `VIEWER`, `SYSTEM_ADMIN`.
  `User.is_officer()` = active + approved + (officer|supervisor).
  `User.can_approve()` = `is_officer()`. Account approval status
  (`PENDING/APPROVED/REJECTED/SUSPENDED`) is re-checked on every request by
  `AccountStatusMiddleware`.
- **Advisory lifecycle:** `Advisory.status` with soft-delete
  (`objects` excludes deleted, `all_objects` includes them). `content_version`
  is an optimistic-concurrency guard — an approval must target the version the
  officer reviewed, and is re-checked under a `select_for_update` lock.
- **Approval gate:** `OfficerApproval` rows are the audit trail; the advisory
  status advances atomically with the approval row.
- **Audit:** every operational action is logged via `apps.audit.service.log_audit_event`.

## Running

```bash
make setup      # create .venv, install deps
make db         # migrate
make fixtures   # seed Kachieng demo data
make test       # pytest
make run        # dev server
```

Tests use `config.settings.development` with `LLM_PROVIDER=none` and
`MAJISHAMBA_SYNC_RUN=1` (advisory runs execute synchronously, no network).

## Current phase: Base44 public API (feature/base44-api)

Branch `feature/base44-api` adds a scoped, token-authenticated REST API at
`/api/v1/` so an external app (e.g. one built on Base44) can request advisory
runs and record officer approvals without a Django session. The web views and
the API now share domain services (`apps.advisories.services.request_advisory_run`,
`apps.approvals.services.record_approval`). Design and rollout details are in
`docs/implementation/`. The test/validation log is `TEST_AND_VALIDATION_LOG.md`.
