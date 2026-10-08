# Kachieng AI Agent

> Climate-smart advisories. Extension officers decide.
>
> Designed for the **Nyatike Sub-County Agricultural Office** (intended user, not a confirmed partner), serving smallholder farmer clusters in **Kachieng Ward, Migori County, Kenya**.

**Track:** African Agentic AI Design Challenge — Agriculture & Food Security
**Sub-theme:** Climate-smart advisory
**Geographic focus:** Migori County → Nyatike Sub-County → **Kachieng Ward**
**Intended user:** Nyatike Sub-County Agricultural Office
**Named user role:** Agricultural Extension Officer
**Licence:** MIT (OSI-approved)

---

## One-sentence pitch

Kachieng AI Agent helps a Nyatike Sub-County Agricultural Extension Officer turn weather, crop-calendar, plot-history and pest signals into a sourced, officer-approved planting advisory for smallholder farmer clusters in Kachieng Ward — **without ever sending advice automatically**.

---

## Get running in one command

### Linux / macOS / WSL / Git Bash

```bash
git clone <your-repo-url> kachieng-ai-agent
cd kachieng-ai-agent
make demo
```

### Windows PowerShell (no `make` required)

```powershell
git clone <your-repo-url> kachieng-ai-agent
cd kachieng-ai-agent
.\scripts\run_demo.ps1
```

> **Note:** `make demo` requires bash (Git Bash on Windows, WSL, or macOS/Linux).
> For native Windows PowerShell, use `scripts\run_demo.ps1` instead — it does the same thing.

Both commands will:
1. Create a Python 3.11+ virtualenv at `.venv/`.
2. Install dependencies (Django, LangGraph, MCP Python SDK, Ollama client, Pydantic, etc.).
3. Apply migrations (defaults to **SQLite** so the demo runs without PostgreSQL/PostGIS).
4. Load synthetic Kachieng Ward fixtures (3 original clusters KACH-01..KACH-03 with 14 households/12 plots, plus weather/pest/market signals).
5. **Seed 14 Kachieng pilot clusters** via the idempotent `seed_kachieng_clusters` management command (renames KACH-01..KACH-03 to the locally-confirmed register; creates KACH-04..KACH-14 with 3 households + 1 plot each).
6. Pull `qwen2.5:7b-instruct` via **Ollama** if installed (skipped gracefully otherwise — the deterministic fallback takes over).
7. Start Django dev server on http://127.0.0.1:8000.

The script **does not seed any demo accounts.** To create a real officer for local testing:

```bash
python manage.py create_officer --username jdoe --full-name "John Doe" --role extension_officer
python manage.py changepassword jdoe
```

Then open http://127.0.0.1:8000/accounts/login/ and sign in with the account you just created.

> If Ollama is not installed, the agent logs `WARN: Ollama not installed` and falls back to a deterministic template generator. The demo still works end-to-end — the model is *one* of two drafting modes.

---

## What this system does (≈300 words for the application form)

**Problem.** The Nyatike Sub-County Agricultural Extension Officer must manually compare rainfall forecasts, crop calendars, plot histories, pest alerts and market prices for many Kachieng smallholder households. Rainfall onset is erratic; false starts cause crop failure or replanting costs. Pest alerts (e.g. fall armyworm) arrive via WhatsApp and radio without cluster specificity. The officer cannot easily show farmers *why* a recommendation was made. The result is generic, late or conflicting advice, with limited auditability.

**Solution.** Kachieng AI Agent is an MCP-based agentic system that gathers evidence through a custom MCP server (`majishamba-extension-mcp`, eight tools), uses **LangGraph** as the orchestration framework, drafts a structured advisory with the open-weights model **Qwen2.5-7B-Instruct via Ollama** (with a deterministic template fallback), validates the output against a strict Pydantic schema, and saves the advisory as **DRAFT**. A named Nyatike extension officer then reviews, edits, approves, defers or rejects it in a Django UI. Only after approval can a follow-up task (e.g. field visit, cluster meeting) be created — the action tool `create_follow_up_task_after_approval` enforces this gate in code. The agent never sends SMS, places orders or issues credit flags; the officer decides how to communicate.

**Sub-theme.** Climate-smart advisory (Agriculture & Food Security).

**Workflow it serves.** The Nyatike Sub-County Agricultural Office's seasonal planting advisory cycle for Kachieng Ward clusters (KACH-01 through KACH-14, 14 locality-based farmer clusters). It focuses on short-rains maize, the dominant staple, in the Migori Low-to-Mid Altitude bimodal zone. All household and plot records are synthetic; weather/pest/market aggregates are clearly labelled. Locality names are confirmed by the project owner (who is from the area); farmer groups are not real organisations.

**Benefits.** Faster advisory preparation, sourced and defensible advice citing rainfall, calendar, plot and pest sources, visibility of data gaps, consistent workflow and an audit trail for the office, and better climate resilience for Kachieng farmers — while keeping the human officer fully responsible.

---

## Problem, solution, benefits (Kachieng-specific)

### Problem

- The Nyatike extension officer must manually compare rainfall forecasts, crop calendars, plot histories, pest alerts and market prices for many Kachieng households.
- Rainfall onset in Nyatike is erratic; false starts cause crop failure or replanting costs.
- Pest alerts (e.g. fall armyworm) arrive via WhatsApp/radio **without cluster specificity**.
- The officer cannot easily show farmers *why* a recommendation was made.
- **Result:** generic, late or conflicting advice; some farmers plant too early/late; limited auditability.

### Solution

- An MCP-based agentic system gathers evidence through a custom MCP server (8 tools), uses LangGraph for multi-step planning, drafts a structured advisory with Qwen2.5-7B-Instruct via Ollama, and requires officer approval before any advisory record or task is created.
- All household/plot data is **synthetic** but geographically realistic for Kachieng Ward.
- The agent **never** sends messages or places orders; the officer decides how to communicate advice.

### Benefits

- Faster advisory preparation for the officer.
- Sourced, defensible advice citing rainfall, calendar, plot and pest sources.
- Visibility of data gaps (missing plot records, stale sources).
- Consistent workflow and audit trail for the office.
- Better climate resilience for Kachieng farmers through better-aligned planting windows and pest monitoring.
- No over-automation: human officer remains responsible.

---

## Stack

| Layer | Choice |
|---|---|
| Backend | Django 5 with custom user model, ORM, admin |
| GIS | GeoDjango-aware; demo uses SQLite + lat/lon floats so PostGIS is optional |
| Database | PostgreSQL/PostGIS in production; SQLite in demo |
| Frontend | Django templates + HTMX, server-rendered, minimal JS |
| Styling | Tailwind CSS (CDN for the demo) |
| Mapping | MapLibre GL JS |
| Orchestration | LangGraph (Python) |
| Custom MCP server | `majishamba-extension-mcp` built with the official MCP Python SDK |
| Borrowed MCP server | Official filesystem MCP server (restricted to `docs/calendars/`) |
| Open-weights model | Qwen2.5-7B-Instruct via Ollama |
| Fallback | Deterministic template generator when model is unavailable |
| Queue/cache | Valkey (Redis-compatible) — **production only**; demo uses local-memory fallback |
| Background jobs | Django-RQ — **production only**; demo runs jobs inline |
| Tests | pytest + pytest-django; Playwright for browser |
| Quality | Ruff, Black, mypy |
| Security scans | pip-audit, Semgrep CE, Gitleaks (external) |
| Licence | MIT |

---

## MCP servers (custom + borrowed)

### Custom: `majishamba-extension-mcp`

Eight tools, all logged to `AuditEvent`:

| Tool | Type | Purpose |
|---|---|---|
| `get_cluster_plot_history` | read | Plot history for a Kachieng cluster |
| `get_crop_calendar` | read | Planting window + activities (maize, short rains) |
| `get_weather_and_rainfall_context` | read | Rainfall + 10-day forecast for Nyatike |
| `get_pest_alerts` | read | Active pest alerts in Migori/Nyanza |
| `get_market_price_context` | read | Maize prices at Migori Town |
| `validate_advisory_evidence` | read | Validates required evidence + staleness |
| `create_draft_advisory_record` | **action** | Persists a DRAFT advisory (no message sent) |
| `create_follow_up_task_after_approval` | **action, approval-gated** | Creates a follow-up task only after a valid `OfficerApproval(decision=APPROVED)` exists |

Each call logs: tool name, sanitised inputs, summarised outputs, timestamp, actor, approval status.

### Borrowed: official filesystem MCP server

> We use the official filesystem MCP server to load approved crop-calendar documents during development because it provides safe, tested file access without building a custom document loader.

Restricted to `docs/calendars/` in development; **never** exposed in production. The custom agent does not depend on it for the demo — the demo uses the calendar stored in the database via `get_crop_calendar`. It exists to satisfy the "borrowed MCP server" requirement and demonstrate MCP craft.

---

## Open-weights model statement

At least **one full end-to-end advisory generation task** is performed by **Qwen2.5-7B-Instruct via Ollama**. The `draft_advisory` LangGraph node calls `ollama.Client(host=OLLAMA_HOST).generate(model="qwen2.5:7b-instruct", ...)`. If Ollama is unavailable, the node falls back to a deterministic template generator and the `generation_mode` field on the Advisory record is set to `fallback_template`. The demo shows this fallback path explicitly.

See `EVALS.md` Task 10 for the degraded-mode test.

---

## Human approval gate (non-negotiable)

The agent **never** sends advice, places orders, or issues credit flags. The workflow:

1. Agent creates an `Advisory` with `status="DRAFT"`.
2. The named Nyatike extension officer reviews it in the Django UI.
3. Officer can approve, edit, reject, defer, or request more evidence.
4. Only after approval does the system allow creation of:
   - An `Advisory` record with `status="APPROVED"`.
   - An optional `FollowUpTask` (field visit / cluster meeting / re-evidence / printed advisory).
5. Officer decides delivery channel (SMS, USSD, call, visit, printed advisory). **The system does not automate this.**

Enforced in code: `apps/tasks/service.py:create_follow_up_task_after_approval` checks for a valid `OfficerApproval(decision=APPROVED)` row before any `FollowUpTask` is created. The MCP action tool `create_follow_up_task_after_approval` calls this function; it cannot be bypassed.

See `docs/governance/human_approval_policy.md` for the full policy.

---

## Demo video

A shot-by-shot plan and narration script for an **unedited under-3-minute demo** is in `docs/operations/demo_script.md`. It shows:
- One-command setup (`make demo`) and the Kachieng context.
- The Nyatike officer requesting an advisory for KACH-01.
- MCP tool calls rendered on screen (plot history, crop calendar, Nyatike weather, Migori pest alerts, Migori Town market prices).
- Draft advisory with evidence, gaps and Kachieng-specific recommendations.
- Officer approval + follow-up task creation (the gate works).
- One failure/retry path and the open-weights model run.

---

## Synthetic data notice

**All household and plot records in this repository are SYNTHETIC.** No real Nyatike household names, plot coordinates, phone numbers, or yields are used. The fixtures (`data/fixtures/*.json`) clearly mark this in `notes` and in the names (`Synthetic rep — Kamau M.`, `Synthetic — Head A`, etc.).

Aggregate weather, pest and market signals are synthetic summaries inspired by publicly-known sources (KMD, KALRO, PlantVillage, TAMSAT, CHIRPS) but are **not** fetched live; they are baked into fixtures so the demo is reproducible.

A real pilot would replace these fixtures with consented data feeds — see `docs/governance/synthetic_data_notice.md` for the consent, privacy and security plan.

---

## Challenge compliance checklist

| # | Requirement | Where it's implemented |
|---|---|---|
| 1 | Own MCP server with ≥3 tools, ≥1 action tool | `apps/mcp_tools/` — 8 tools, 2 action tools (`create_draft_advisory_record`, `create_follow_up_task_after_approval`) |
| 2 | One borrowed MCP server (community/official/vendor) | Official filesystem MCP server, restricted to `docs/calendars/`. Justification in `ARCHITECTURE.md` |
| 3 | Open-source orchestration (LangGraph) | `apps/agents/graph.py` — LangGraph `StateGraph` with 11 nodes |
| 4 | One full task on an open-weights model (Qwen2.5-7B via Ollama) | `apps/agents/graph.py:draft_advisory` calls Ollama; demo + `EVALS.md` show it |
| 5 | Logged tool call for every action | `apps/audit/service.py:log_tool_call` + `AuditEvent` rows |
| 6 | Gate on every irreversible action | `apps/tasks/service.py` enforces `OfficerApproval(decision=APPROVED)` |
| 7 | Public repo, OSI-approved licence (MIT) | `LICENSE`, MIT |
| 8 | Demo video plan + script | `docs/operations/demo_script.md` |
| 9 | Text description (~300 words) | README "What this system does" section above |
| 10 | `ARCHITECTURE.md` | `ARCHITECTURE.md` (one page) |
| 11 | `EVALS.md` ≥8 tasks + 1 unresolved failure | `EVALS.md` (10 tasks + 1 unresolved) |
| 12 | New work built during submission period | Fresh repo `majishamba/` — no existing project claimed as new |
| 13 | Synthetic data conduct | Fixtures labelled; `docs/governance/synthetic_data_notice.md` |

---

## Documentation map

- `README.md` (this file)
- `ARCHITECTURE.md` — one-page architecture overview
- `EVALS.md` — 10 test tasks + 1 unresolved failure
- `docs/product/problem_statement.md`
- `docs/product/solution_overview.md`
- `docs/product/kachieng_context.md`
- `docs/product/user_research.md`
- `docs/architecture/system_architecture.md`
- `docs/architecture/mcp_architecture.md`
- `docs/architecture/data_flow.md`
- `docs/governance/ai_governance.md`
- `docs/governance/human_approval_policy.md`
- `docs/governance/synthetic_data_notice.md`
- `docs/operations/developer_setup.md`
- `docs/operations/demo_script.md`

---

## Repository structure

```text
majishamba/
├── README.md            · this file
├── LICENSE              · MIT
├── ARCHITECTURE.md      · one-page architecture
├── EVALS.md             · evaluation plan
├── pyproject.toml       · deps + tool config
├── manage.py            · Django entry
├── Makefile             · `make demo` target
├── config/              · Django settings (base/dev/prod), urls, asgi, wsgi
├── apps/
│   ├── accounts/        · custom user, roles
│   ├── geography/       · counties/sub-counties/wards/office
│   ├── clusters/        · KACH-01..03, households
│   ├── plots/           · plots + season records
│   ├── calendars/       · Migori maize calendars
│   ├── weather/         · Nyatike weather signals
│   ├── pests/           · Migori pest alerts
│   ├── markets/         · Migori Town market prices
│   ├── advisories/      · advisory drafts + evidence
│   ├── approvals/       · officer approval gate
│   ├── tasks/           · follow-up tasks (approval-gated)
│   ├── agents/          · LangGraph agent
│   ├── mcp_tools/       · custom MCP server (8 tools)
│   ├── audit/           · audit event log + middleware
│   └── dashboard/       · officer dashboard views
├── templates/           · Django templates (Tailwind via CDN)
├── static/              · css/js/images
├── data/fixtures/       · synthetic Kachieng fixtures
├── scripts/             · setup_ollama.sh, load_demo_data.py, run_demo.sh, smoke_test.py
├── docs/                · product / architecture / governance / operations
│   └── calendars/       · borrowed filesystem MCP root
└── tests/               · conftest, factories, integration, security, e2e
```

---

## Creating an officer account

The setup scripts no longer seed any synthetic demo accounts. To create a real
officer for local testing or production, use the management command and then
set a password interactively (the password is never stored in scripts or
fixtures):

```bash
python manage.py create_officer --username jdoe --full-name "John Doe" --role extension_officer
python manage.py changepassword jdoe
```

The account is created with an unusable password — login will fail until you
run `changepassword`. Roles: `extension_officer`, `supervisor`, `viewer`.

### Cleaning up old synthetic demo accounts

If you are upgrading from an older deployment that still has the synthetic
demo accounts (`nyatike_officer`, `nyatike_supervisor`, `nyatike_viewer`),
you can list, deactivate, or delete them safely with the
`cleanup_demo_accounts` management command (see its `--help` for full
options). The command is read-only by default; pass `--confirm` to apply
changes. Audit history is preserved (the `AuditEvent.actor` FK uses
`on_delete=SET_NULL`, so deleting a user leaves the audit row behind with a
NULL actor rather than cascading the delete).

```bash
python manage.py cleanup_demo_accounts                # list only
python manage.py cleanup_demo_accounts --confirm      # deactivate (reversible)
python manage.py cleanup_demo_accounts --confirm --delete  # hard delete (audit rows preserved)
```

---

## 14 Kachieng pilot clusters

The system uses an idempotent management command to seed 14 locality-based farmer clusters:

| Cluster ID | Name | Locality |
|---|---|---|
| KACH-01 | Sori Farmer Cluster | Sori |
| KACH-02 | Kiranda Farmer Cluster | Kiranda |
| KACH-03 | Odendo Farmer Cluster | Odendo |
| KACH-04 | Agolomuok Farmer Cluster | Agolomuok |
| KACH-05 | Bongu Farmer Cluster | Bongu |
| KACH-06 | Gunga Farmer Cluster | Gunga |
| KACH-07 | Kaduro Farmer Cluster | Kaduro |
| KACH-08 | Kopala Farmer Cluster | Kopala |
| KACH-09 | Nyamanga Farmer Cluster | Nyamanga |
| KACH-10 | Obondi Farmer Cluster | Obondi |
| KACH-11 | Orore Farmer Cluster | Orore |
| KACH-12 | Raga Farmer Cluster | Raga |
| KACH-13 | Sidika Farmer Cluster | Sidika |
| KACH-14 | Wachara Farmer Cluster | Wachara |

**Geographic verification record:**

```
verification_status: locally_confirmed
verification_method: project_owner_local_knowledge
verified_by: Onunga Christopher
verification_date: 2026-10-06
geographic_type: locality
```

Locality names are confirmed by the project owner (who is from the area). This does NOT constitute government certification, administrative classification, or coordinates. All farmer groups, household records, plot histories and yields are explicitly synthetic. **No coordinates are invented** for new clusters — they appear in the locality list with "Coordinates not yet recorded" until real verified coordinates are collected.

### Re-seeding (idempotent)

```bash
python manage.py seed_kachieng_clusters            # apply
python manage.py seed_kachieng_clusters --dry-run  # preview only
python manage.py seed_kachieng_clusters --report    # show current totals
```

The command:
- Preserves KACH-01..KACH-03 primary keys, households, plots, advisories, audit history
- Updates KACH-01..KACH-03 display names and `locality` field
- Creates KACH-04..KACH-14 with three synthetic households each, one synthetic maize plot per household
- Is idempotent — running twice produces no duplicates
- Does NOT reset the database or overwrite existing household records

---

## Quick commands

| Command | What it does |
|---|---|
| `make demo` | One-command demo: deps → migrate → fixtures → ollama → runserver |
| `make test` | Run pytest suite |
| `make lint` | Ruff + Black --check |
| `make typecheck` | mypy |
| `make security` | pip-audit + Semgrep CE + Gitleaks (if installed) |
| `make reset-demo` | Reset the SQLite DB and reload fixtures |
| `python scripts/smoke_test.py` | End-to-end smoke test (runs the agent + approval + task) |

---

## Contributing

Issues and pull requests welcome. All contributions must keep the human-in-the-loop invariant: no automated outbound messages, no auto-approval, no auto-task creation.

## Licence

MIT — see `LICENSE`.
