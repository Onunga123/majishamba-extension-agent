# Kachieng AI Agent

> Climate-smart advisories. Extension officers decide.

## About

MajiShamba Extension Agent is a human-in-the-loop Django and LangGraph platform that helps agricultural extension officers create evidence-based, climate-smart advisories for farmers in Kachieng Ward, Nyatike Sub-County, Migori County, Kenya. It combines weather, pest, market, crop-calendar, and farm data through MCP tools, while ensuring that every advisory is reviewed and approved by a qualified officer before follow-up actions are created.

**Licence:** MIT (OSI-approved)

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
5. **Seed 14 Kachieng pilot clusters** via the idempotent `seed_kachieng_clusters` management command (renames KACH-01..KACH-03 to the locally-confirmed register; creates KACH-04..KACH-14 with 3 h[...]
6. Select the configured provider: OpenRouter cloud inference is recommended for laptops; Ollama remains an optional local alternative; `none` selects deterministic fallback only.
7. Start Django dev server on http://127.0.0.1:8000.

The script **does not seed any demo accounts.** To create a real officer for local testing:

```bash
python manage.py create_officer --username jdoe --full-name "John Doe" --role extension_officer
python manage.py changepassword jdoe
```

Then open http://127.0.0.1:8000/accounts/login/ and sign in with the account you just created.

> Provider failures never silently switch to another model. The advisory records `llm_openrouter`, `llm_ollama`, or `fallback_template`; an OpenRouter failure is still a fallback advisory, not a s[...]

## LLM execution modes

### Option A — OpenRouter cloud inference (recommended for this demo)

OpenRouter lets the application run on a computer without local model hardware. It uses the official chat-completions endpoint and the configured model identifier.

1. Create an account and API key at [OpenRouter](https://openrouter.ai/keys).
2. Copy `.env.example` to `.env` (never commit `.env`).
3. Set these values in your local `.env`:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=openrouter/free
```

You may instead set a specific available model ending in `:free`, for example `provider/model:free`. Free-model availability, rate limits, context limits and structured-output behavior vary. The a[...]

For a one-session PowerShell setup without putting the key in a tracked file:

```powershell
$env:LLM_PROVIDER = "openrouter"
$env:OPENROUTER_MODEL = "openrouter/free"
$env:OPENROUTER_API_KEY = Read-Host "OpenRouter API key"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

### Option B — Ollama local inference

Ollama remains supported for developers with compatible hardware and is the local open-weights path:

```powershell
# Install Ollama from https://ollama.com, then:
ollama pull qwen2.5:7b-instruct
$env:LLM_PROVIDER = "ollama"
$env:OLLAMA_HOST = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "qwen2.5:7b-instruct"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Use `LLM_PROVIDER=none` for deterministic fallback-only operation. OpenRouter remote inference—even when the remote model has open weights—is **not automatically evidence** that the Agricultur[...]

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
| Cloud demo model | OpenRouter `openrouter/free` or configured `:free` model |
| Local open-weights model | Qwen2.5-7B-Instruct via Ollama |
| Fallback | Deterministic template generator when model is unavailable |
| Queue/cache | Valkey (Redis-compatible) — **production only**; demo uses local-memory fallback |
| Background jobs | Django-RQ — **production only**; demo runs jobs inline |
| Tests | pytest + pytest-django; Playwright for browser |
| Quality | Ruff, Black, mypy |
| Security scans | pip-audit, Semgrep CE, Gitleaks (external) |
| Licence | MIT |

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

Restricted to `docs/calendars/` in development; **never** exposed in production. The custom agent does not depend on it for the demo — the demo uses the calendar stored in the database via `get[...]

## Open-weights model statement

The application supports a full advisory task through OpenRouter cloud inference and preserves **Qwen2.5-7B-Instruct via Ollama** as the local open-weights path. The `generation_mode` field disti[...]

See `EVALS.md` Task 10 for the degraded-mode test.
## Human approval gate 

The agent **never** sends advice, places orders, or issues credit flags. The workflow:

1. Agent creates an `Advisory` with `status="DRAFT"`.
2. The named Nyatike extension officer reviews it in the Django UI.
3. Officer can approve, edit, reject, defer, or request more evidence.
4. Only after approval does the system allow creation of:
   - An `Advisory` record with `status="APPROVED"`.
   - An optional `FollowUpTask` (field visit / cluster meeting / re-evidence / printed advisory).
5. Officer decides delivery channel (SMS, USSD, call, visit, printed advisory). **The system does not automate this.**

Enforced in code: `apps/tasks/service.py:create_follow_up_task_after_approval` checks for a valid `OfficerApproval(decision=APPROVED)` row before any `FollowUpTask` is created. The MCP action too[...]

See `docs/governance/human_approval_policy.md` for the full policy.

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
| `make demo` | One-command demo: deps → migrate → fixtures → configured provider → runserver |
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
