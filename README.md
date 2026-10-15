# Kachieng' AI Agent

**Climate-smart advisories**

Kachieng' AI Agent is an agentic AI system designed to help agricultural extension officers prepare climate-smart advisory drafts, organise available agricultural information, coordinate human review, and support geographic orientation and field follow-up.

The project addresses the Agriculture track challenge, "The Extension Backlog," in the [African Agentic AI Design Challenge](https://agentic-africa-challenge.lovable.app/tracks/agriculture).

**Repository:** https://github.com/Onunga123/majishamba-extension-agent

**Licence:** MIT (OSI-approved) — see [LICENSE](LICENSE)

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Solution Overview](#solution-overview)
- [Target Users](#target-users)
- [Features](#features)
- [Architecture](#architecture)
- [Agentic AI Architecture](#agentic-ai-architecture)
- [MCP Implementation](#mcp-implementation)
- [Human-in-the-Loop Workflow](#human-in-the-loop-workflow)
- [Geographic Mapping and Field Follow-Up](#geographic-mapping-and-field-follow-up)
- [African Context](#african-context)
- [Setup and Installation](#setup-and-installation)
- [Configuration](#configuration)
- [Usage Instructions](#usage-instructions)
- [Technology Stack](#technology-stack)
- [Data Sources, Privacy, and Limitations](#data-sources-privacy-and-limitations)
- [Testing and Evaluation](#testing-and-evaluation)
- [Limitations](#limitations)
- [Future Improvements](#future-improvements)
- [Licence, Security, and Responsible Use](#licence-security-and-responsible-use)
- [Contributing](#contributing)
- [Documentation Map](#documentation-map)

---

## Problem Statement

Agricultural extension officers in resource-constrained African communities often face a growing backlog of farmer support requests, limited time for field visits, and fragmented access to weather, crop, pest, and market information. These challenges can slow the preparation of relevant agricultural advisories and make it difficult to coordinate follow-up across geographically dispersed farming communities.

The problem is particularly important where officers serve multiple farmer groups with limited resources and must make decisions using incomplete or unverified information. New officers may also need support understanding the locations of farmer clusters and planning field follow-up.

Kachieng' AI Agent addresses this workflow bottleneck by helping officers prepare climate-smart advisory drafts, organise information for review, and connect advisory workflows with geographic mapping and follow-up activities. Human review remains essential before recommendations proceed to operational use.

---

## Solution Overview

Kachieng' AI Agent is an agentic AI system that supports agricultural extension officers in preparing and managing climate-smart advisories. It brings together available information — weather conditions, plot history, crop-calendar material, pest alerts, and market context — to help generate advisory drafts. Evidence validation helps identify missing, unverified, or unauthorised information instead of presenting every output as confirmed.

The workflow includes role-based access for Extension Officers, Supervisors, System Administrators, and Viewers. Officers can prepare and inspect advisories, while authorised reviewers provide human oversight before operational follow-up. Geographic mapping helps officers understand the service area, locate farmer clusters, and plan field visits. Recorded activity supports traceability across relevant workflow actions.

The system is designed to support professional judgement, not replace it. This demonstration uses synthetic household and plot data, not real farmer household records.

### Key Distinction: AI Drafts vs. Human Decisions

AI-generated drafts are **not** automatically equivalent to approved agricultural recommendations. The agent prepares a draft; a named officer reviews, edits, and decides. Only after human approval can follow-up actions proceed. The agent never sends messages, places orders, or issues credit flags.

---

## Target Users

| Role | Responsibilities |
|------|-----------------|
| **Extension Officer** | Request advisories, review drafts, inspect evidence, manage field tasks, record field findings |
| **Supervisor** | Review and approve/reject/defer advisories, verify field findings (cannot self-verify own findings) |
| **System Administrator** | Manage user accounts, review account requests, access the full audit log |
| **Viewer** | Read-only access to dashboards, advisories, and tasks (officer names redacted to role labels) |

> Permissions are enforced server-side via application-role checks (`is_officer()`, `is_system_admin()`, `can_approve()`), not Django's `is_staff` flag. The `create_officer` provisioning command sets `is_staff=False` for all roles.

---

## Features

- **AI-assisted climate-smart advisory generation** — The LangGraph agent calls 6 read-only tools to gather evidence, invokes an open-weights model (Qwen 2.5 7B Instruct via OpenRouter or Ollama), and drafts a structured advisory with evidence citations.
- **Agricultural context retrieval** — Plot history, crop calendars, weather signals, pest alerts, and market prices are retrieved through MCP tools.
- **Evidence and output validation** — The agent validates evidence completeness, source staleness, and output schema (Pydantic). Missing or stale sources are flagged, not hidden.
- **Geographic mapping** — A MapLibre GL JS map shows farmer clusters with locality names and verification status, helping officers orient and plan field visits.
- **Human review and approval** — Every advisory is saved as DRAFT. An authorised officer reviews, edits, approves, rejects, defers, or requests more evidence. No farmer message is ever sent.
- **Field follow-up and task management** — After approval, a follow-up task (field visit, cluster meeting) can be created. Officers record field findings; supervisors verify them.
- **Role-based access control** — Four roles with server-side enforcement. Viewers see redacted officer names and cannot access field-finding content.
- **Audit trail** — Every tool call, approval decision, task action, and agent run is logged to `AuditEvent` with actor, timestamp, and sanitised inputs.

---

## Architecture

A landscape architecture diagram is available at [`docs/architecture/kachieng_ai_agent_architecture.pdf`](docs/architecture/kachieng_ai_agent_architecture.pdf) and [`docs/architecture/kachieng_ai_agent_architecture.png`](docs/architecture/kachieng_ai_agent_architecture.png).

See also: [ARCHITECTURE.md](ARCHITECTURE.md) for the one-page written architecture reference.

### Components

| Component | Technology | Role |
|-----------|-----------|------|
| Web application | Django 5.1 | User interface, authentication, advisory workflow, map, task management |
| Agent orchestration | LangGraph (`StateGraph`) | 12-node pipeline with conditional routing and human gate |
| LLM provider | OpenRouter (cloud) or Ollama (local) | Drafts advisory JSON from gathered evidence |
| Open-weights model | Qwen 2.5 7B Instruct (Apache 2.0) | Generates structured advisory drafts |
| Custom MCP server | `majishamba-extension-mcp` (MCP Python SDK / FastMCP) | Exposes 8 tools over stdio |
| Borrowed MCP server | `@modelcontextprotocol/server-filesystem` | Reads crop-calendar files from `docs/calendars/` |
| Database | SQLite (default) or PostgreSQL/PostGIS (optional) | Advisory, evidence, approval, task, audit records |
| External API | Open-Meteo (optional) | Live weather forecast retrieval |
| Frontend | Django templates + HTMX + Tailwind CSS (CDN) | Server-rendered, minimal JS |
| Mapping | MapLibre GL JS + CARTO raster tiles | Cluster map with locality orientation |

### Data Flow

```
Extension Officer (browser) → Django view → LangGraph agent
    → 6 read-only MCP tool calls (plot, calendar, weather, pest, market, validate)
    → Borrowed filesystem MCP (crop-calendar files)
    → LLM call (OpenRouter/Ollama/fallback) → Pydantic validation
    → Draft persisted → Officer review → Approval gate
    → Follow-up task (if approved) → Field findings → Supervisor verification
    → All actions logged to AuditEvent
```

---

## Agentic AI Architecture

Kachieng' AI Agent executes a coordinated, multi-step advisory workflow rather than relying on a single prompt-and-response interaction. LangGraph orchestrates the workflow through 12 named nodes connected by directed edges and conditional transitions.

### Pipeline Nodes (in execution order)

| # | Node | What It Does |
|---|------|-------------|
| 1 | `validate_request` | Checks cluster exists; routes to gate on error |
| 2 | `fetch_plot_history` | Calls `get_cluster_plot_history` tool |
| 3 | `fetch_crop_calendar` | Calls `get_crop_calendar` tool |
| 4 | `load_calendar_from_borrowed_mcp` | Uses borrowed filesystem MCP server |
| 5 | `fetch_weather` | Calls `get_weather_and_rainfall_context` tool |
| 6 | `fetch_pest_alerts` | Calls `get_pest_alerts` tool |
| 7 | `fetch_market_prices` | Calls `get_market_price_context` tool |
| 8 | `validate_evidence` | Calls `validate_advisory_evidence` tool |
| 9 | `draft_advisory` | Calls LLM (OpenRouter/Ollama) or uses fallback template |
| 10 | `validate_output_schema` | Validates LLM output as JSON against Pydantic `AdvisoryDraft` |
| 11 | `save_draft` | Calls `create_draft_advisory_record` to persist DRAFT advisory |
| 12 | `officer_approval_gate` | Stops — human review required outside the graph |

### Conditional Routing

- If `validate_request` finds errors → route directly to `officer_approval_gate` (skip pipeline)
- If `draft_advisory` LLM call fails → fallback to `use_fallback_template` → re-validate
- If `validate_output_schema` finds invalid JSON → route to `use_fallback_template`
- After `save_draft` → route to `officer_approval_gate` → END

The agent does not independently verify real-world facts. It retrieves available data through tools, drafts based on that data, and validates the output structure. Human review remains the authoritative decision point.

---

## MCP Implementation

Kachieng' AI Agent integrates Model Context Protocol (MCP) to provide a structured way for the agent to access application-specific tools. The agent workflow uses MCP tool access to communicate with a custom MCP server exposing capabilities such as advisory-record creation, evidence validation, pest-alert retrieval, and market-context retrieval.

### Custom MCP Server: `majishamba-extension-mcp`

Built with the official **MCP Python SDK** (`mcp.server.fastmcp.FastMCP`) in `apps/mcp_tools/server.py`. Exposes 8 tools over stdio to any MCP-aware client (Claude Desktop, test harness, partner agent). The server is intentionally thin — it delegates to the same `TOOL_REGISTRY` functions that the agent and Django views call.

### Eight Tools (6 read-only, 2 action)

| Tool | Type | Purpose |
|------|------|---------|
| `get_cluster_plot_history` | Read | List plots and crop season records for a farmer cluster |
| `get_crop_calendar` | Read | Get recommended planting window for a crop in a Migori zone/season |
| `get_weather_and_rainfall_context` | Read | Get rainfall and forecast signals for Nyatike sub-county |
| `get_pest_alerts` | Read | Get active pest alerts for a crop in Migori County |
| `get_market_price_context` | Read | Get recent maize price signals at Migori Town market |
| `validate_advisory_evidence` | Read | Validate that an advisory cites required evidence and is not stale |
| `create_draft_advisory_record` | **Action** | Persist a DRAFT advisory record (no farmer message sent) |
| `create_follow_up_task_after_approval` | **Action (gated)** | Create a follow-up task — requires `OfficerApproval(decision=APPROVED)` |

Each tool call logs to `AuditEvent` with: tool name, sanitised inputs (prompt-injection patterns stripped), summarised outputs, timestamp, actor ID, and approval status.

### Borrowed MCP Server: Official Filesystem MCP Server

The official `@modelcontextprotocol/server-filesystem` is used in the `load_calendar_from_borrowed_mcp` graph node to read approved crop-calendar documents from `docs/calendars/`. It is restricted to that directory via `MAJISHAMBA_BORROWED_FILESYSTEM_MCP_ROOT`. When Node/npx is unavailable, the node reads the file directly as a dev fallback but still logs the call to the audit trail as `borrowed_filesystem_mcp`.

### MCP Resources and Prompts

No MCP resources or prompts are explicitly implemented. The MCP server exposes only tools.

### How Tool Results Enter the Workflow

Each tool returns a dict that updates the agent state. Subsequent nodes read from state — for example, `validate_evidence` reads `state.weather`, `state.crop_calendar`, `state.pest_alerts`, and `state.market_prices` to check completeness and staleness. The `draft_advisory` node builds the LLM prompt from all gathered evidence in state.

### Error Handling and Limitations

- If a tool returns warnings (e.g., "No plot records found"), they are added to `state.warnings` and surfaced in the advisory's `limitations` section.
- If the LLM call fails (timeout, rate limit, invalid output), the agent falls back to a deterministic template and records `generation_mode = "fallback_template"`.
- If the borrowed filesystem MCP server is unavailable (no Node/npx), the node reads the calendar file directly as a dev fallback.
- MCP tool access does not itself verify the truth of external information — evidence limitations and human oversight remain important.

---

## Human-in-the-Loop Workflow

1. The **Extension Officer** initiates an advisory request through the Django web application (`/advisories/request/`).
2. The **agent** retrieves available context (plot history, crop calendar, weather, pest alerts, market prices), validates evidence, and prepares a draft using the open-weights model.
3. The **application** validates the draft output against a Pydantic schema and persists it as `status="DRAFT"`.
4. The draft is presented for review by an authorised officer (Extension Officer or Supervisor) at the approval gate (`/approvals/<pk>/`).
5. The **reviewer** can: **Approve**, **Reject**, **Defer**, or **Request more evidence**. The page explicitly states "No farmer message will be sent."
6. Only after **approval** can a follow-up task be created — the `create_follow_up_task_after_approval` tool checks for a valid `OfficerApproval(decision=APPROVED)` record.
7. After approval, a **FollowUpTask** (field visit, cluster meeting) can be created. The officer records field findings; a Supervisor verifies them.
8. All actions — tool calls, approval decisions, task state changes — are recorded to the `AuditEvent` log with actor, timestamp, and decision metadata.

### Generated Drafts vs. Authorised Recommendations

AI-generated drafts are **not** approved recommendations. They are evidence-based starting points for officer review. The officer decides whether the draft is accurate, whether to edit it, and whether to approve it. The system never sends advice to farmers automatically.

---

## Geographic Mapping and Field Follow-Up

The geographic map (`/dashboard/map/`) provides a spatial view of the service area and farmer clusters. It is intended to help extension officers, including newly assigned officers, familiarise themselves with the area and plan field follow-up.

### Map Features

- **MapLibre GL JS** with CARTO Voyager raster tiles.
- Clusters with approved coordinates appear as map markers with locality names.
- Clusters without coordinates appear in a list with "Coordinates not yet recorded."
- Each marker shows cluster ID, locality name, household count, and coordinate verification status.
- A locality list JSON endpoint (`/geo/localities.json`) provides the same data for programmatic use.

### Limitations

The map supports geographic orientation; it does not replace local directions, field verification, or the officer's knowledge of local conditions. Turn-by-turn navigation and live farmer GPS tracking are not implemented.

---

## African Context

The solution is designed around smallholder agriculture and agricultural extension work in Kenya, using Kachieng' Ward in Nyatike Sub-County, Migori County, as its demonstration context. Farming decisions are influenced by local weather, seasonal crop calendars, pest risks, access to agricultural guidance, and market conditions. Extension officers must coordinate support across farmer clusters while working within practical time and resource constraints.

The design emphasises climate-smart advisories, geographic awareness for field navigation, evidence limitations, and human oversight. The demonstration uses synthetic household and plot data rather than real farmer household records. Local conditions and recommendations still require appropriate verification.

### 14 Kachieng Pilot Clusters

| Cluster ID | Locality |
|------------|----------|
| KACH-01 | Sori |
| KACH-02 | Kiranda |
| KACH-03 | Odendo |
| KACH-04 | Agolomuok |
| KACH-05 | Bongu |
| KACH-06 | Gunga |
| KACH-07 | Kaduro |
| KACH-08 | Kopala |
| KACH-09 | Nyamanga |
| KACH-10 | Obondi |
| KACH-11 | Orore |
| KACH-12 | Raga |
| KACH-13 | Sidika |
| KACH-14 | Wachara |

Locality names are confirmed by the project owner (who is from the area). All farmer groups, household records, plot histories, and yields are explicitly synthetic.

---

## Setup and Installation

### Prerequisites

- **Python 3.11+** — must be on PATH as `python` (Windows) or `python3` (Linux/macOS)
- **Git** — to clone the repository
- **`make`** — required on Linux/macOS/WSL/Git Bash. On Windows PowerShell, use `.\scripts\run_demo.ps1` instead (no `make` needed)

No database, API key, or external service is required for the demo. The application uses SQLite by default and falls back to a deterministic template generator when no LLM provider is configured.

### Quick Start (One Command)

#### Linux / macOS / WSL / Git Bash

```bash
git clone https://github.com/Onunga123/majishamba-extension-agent.git
cd majishamba-extension-agent
make demo
```

#### Windows PowerShell

```powershell
git clone https://github.com/Onunga123/majishamba-extension-agent.git
cd majishamba-extension-agent
.\scripts\run_demo.ps1
```

Both commands will:

1. Create a Python virtualenv at `.venv/` and install all dependencies
2. Apply database migrations (SQLite — no PostgreSQL or PostGIS needed)
3. Load synthetic Kachieng Ward fixtures (clusters, plots, weather, pest, and market data)
4. Seed 14 locality-based farmer clusters
5. Start the Django development server on http://127.0.0.1:8000

### Create an Account and Log In

The setup scripts do not seed any user accounts. After the server is running, open a new terminal in the project directory:

```powershell
# Activate the virtualenv (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Create an officer account
python manage.py create_officer --username jdoe --full-name "John Doe" --role extension_officer
python manage.py changepassword jdoe
```

The account is created with an unusable password — login will fail until you run `changepassword`. The account is immediately approved (no admin review needed for accounts created via this command). Available roles: `extension_officer`, `supervisor`, `viewer`.

To create a System Administrator:

```powershell
python manage.py create_system_admin --username admin --full-name "System Admin"
```

Then open http://127.0.0.1:8000/accounts/login/ and sign in.

### Manual Setup (Step by Step)

```powershell
# 1. Clone
git clone https://github.com/Onunga123/majishamba-extension-agent.git
cd majishamba-extension-agent

# 2. Create virtualenv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Copy .env.example to .env and edit (see Configuration section below)
Copy-Item .env.example .env

# 5. Apply migrations
python manage.py migrate

# 6. Load fixtures
python manage.py loaddata data/fixtures/*.json
python manage.py seed_kachieng_clusters

# 7. Start the dev server
python manage.py runserver
```

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed. **Never commit `.env` to version control.**

### Environment Variables

| Variable | Required? | Default | Purpose |
|----------|-----------|---------|---------|
| `DJANGO_SETTINGS_MODULE` | Yes | `config.settings.development` | Django settings module |
| `MAJISHAMBA_DEBUG` | No | `True` | Debug mode |
| `MAJISHAMBA_SECRET_KEY` | Production | `change-me-in-production` | Django secret key (set a real value in production) |
| `LLM_PROVIDER` | No | `none` | LLM provider: `openrouter`, `ollama`, or `none` |
| `OPENROUTER_API_KEY` | If `openrouter` | — | API key from [openrouter.ai/keys](https://openrouter.ai/keys) |
| `OPENROUTER_MODEL` | No | `qwen/qwen-2.5-7b-instruct` | OpenRouter model identifier |
| `OPENROUTER_TIMEOUT_SECONDS` | No | `120` | Request timeout |
| `OPENROUTER_MAX_OUTPUT_TOKENS` | No | `1500` | Max output tokens |
| `OLLAMA_HOST` | If `ollama` | `http://127.0.0.1:11434` | Ollama server URL |
| `OLLAMA_MODEL` | No | `qwen2.5:7b-instruct` | Ollama model name |
| `CARTO_BASEMAP_API_KEY` | No | — | CARTO basemap API key (visible in browser, not a backend secret) |
| `DEMO_MODE` | No | `1` | Show demo-mode indicator on login page |

### LLM Provider Modes

| Provider | Setting | Requirement |
|----------|---------|-------------|
| **OpenRouter (cloud)** | `LLM_PROVIDER=openrouter` | API key from [openrouter.ai](https://openrouter.ai/keys) — uses the open-weights model Qwen 2.5 7B Instruct via hosted inference |
| **Ollama (local)** | `LLM_PROVIDER=ollama` | [Ollama](https://ollama.com) installed, `ollama pull qwen2.5:7b-instruct` — runs the same open-weights model locally |
| **None (fallback)** | `LLM_PROVIDER=none` | No external service needed — deterministic template generator |

Provider failures never silently switch models. The advisory records the generation mode used (`llm_openrouter`, `llm_ollama`, or `fallback_template`) in the `Advisory.generation_mode` field.

### Open-Weights Model

The configured model, **Qwen 2.5 7B Instruct**, is an open-weights model published under the Apache 2.0 licence on [HuggingFace](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct). The challenge's jargon section explicitly lists Qwen as an example of an open-weights model: *"A model you can download and run yourself. Qwen, Llama, Gemma, Mistral, Aya."*

---

## Usage Instructions

1. **Sign in** at http://127.0.0.1:8000/accounts/login/ with your officer account.
2. **Open the dashboard** at `/dashboard/` — see Kachieng' Ward clusters, advisory statuses, pending tasks, and recent activity.
3. **Request an advisory** — click "Advisories" → "Request advisory" (`/advisories/request/`). Select a cluster (e.g., KACH-01) and submit.
4. **Watch the agent run** — the run status page (`/advisories/runs/<uuid>/`) auto-refreshes every 2 seconds, showing stage progress: "Checking plot records", "Reading maize guidance", "Retrieving weather evidence", etc.
5. **Inspect the draft** — click "Open draft advisory" to view the generated advisory with evidence citations, confidence level, limitations, and generation mode ("LLM-generated (OpenRouter)" or "Template-generated draft").
6. **Review limitations** — check the evidence grid for missing or stale sources. The advisory body includes `[Source: ...]` citations for each claim.
7. **Submit for review** — click "Review and decide" (`/approvals/<pk>/`) to open the approval gate. Choose Approve, Reject, Defer, or Needs more evidence.
8. **Follow-up** — if approved, optionally create a follow-up task (field visit). Record field findings after visiting the cluster. A Supervisor can verify the findings.
9. **Inspect activity history** — the dashboard "Recent activity" feed shows agent runs, approvals, and task actions with timestamps and responsible officer names.
10. **Use the map** — open `/dashboard/map/` to see farmer clusters with locality names and plan field visits.

---

## Technology Stack

| Layer | Technology | Required? |
|-------|-----------|-----------|
| Backend | Django 5.1 (`Django>=5.0,<5.2`) | Yes |
| Agent orchestration | LangGraph (`langgraph>=0.2`) | Yes |
| MCP server | MCP Python SDK (`mcp>=1.0`, FastMCP) | Yes |
| Open-weights model | Qwen 2.5 7B Instruct via OpenRouter or Ollama (`ollama>=0.3`) | Optional (fallback works without it) |
| Database | SQLite (default) | Yes |
| Database (production) | PostgreSQL / PostGIS (optional, `USE_POSTGRES=1`) | No |
| Frontend | Django templates + HTMX + Tailwind CSS (CDN) | Yes |
| Mapping | MapLibre GL JS + CARTO raster tiles | Yes |
| Validation | Pydantic (`pydantic>=2.7`) | Yes |
| HTTP client | httpx (`httpx>=0.27`) | Yes (for Open-Meteo and OpenRouter) |
| External API | Open-Meteo (`https://api.open-meteo.com/v1/forecast`) | Optional (live weather fetch) |
| Background jobs | Django-RQ + Valkey (Redis-compatible) | Production only |
| Testing | pytest + pytest-django | Yes |
| Browser testing | Playwright | Optional (`RUN_PLAYWRIGHT_TESTS=1`) |
| Code quality | Ruff, Black, mypy | Yes (dev) |
| Security scans | pip-audit, Semgrep CE | Optional |
| Licence | MIT | Yes |

---

## Data Sources, Privacy, and Limitations

### Data Sources

| Source | Type | Status |
|--------|------|--------|
| Synthetic fixtures | Demo data (clusters, plots, households, weather, pest, market) | Loaded via `data/fixtures/*.json` |
| `docs/calendars/` | Crop-calendar files | Read by borrowed filesystem MCP server |
| Open-Meteo API | Live weather forecast | Optional integration (`apps/integrations/open_meteo.py`); not used by default demo |
| Database (SQLite/PostgreSQL) | Persistent storage | Advisory, evidence, approval, task, audit records |

### Privacy

- **All household and plot records are synthetic.** No real farmer household names, phone numbers, plot coordinates, or yields are used. See [`docs/governance/synthetic_data_notice.md`](docs/governance/synthetic_data_notice.md).
- The system is designed so that household and yield data does not need to leave the country — OpenRouter is an optional cloud provider; Ollama runs locally.
- API keys are never logged. Prompt-injection patterns are stripped from text fields by `_sanitize_inputs`.

### Evidence Limitations

- Weather observations do not independently establish local field conditions.
- Missing pest notices do not prove that pests are absent.
- Crop-calendar material may be stale (older than 2 years) — the agent flags this.
- Some sources may be unauthorised for operational use (e.g., KALRO guidance is permission-pending).
- The agent's `limitations` section in each advisory honestly documents data gaps and uncertainties.
- Appropriate human review and local field verification remain necessary.

---

## Testing and Evaluation

### Running Tests

```bash
# Full test suite (excluding E2E/browser tests)
pytest --ignore=tests/e2e --ignore=tests/integration/test_browser.py

# Security tests only
pytest tests/security/

# With live Ollama (requires hardware capable of running 7B model)
MAJISHAMBA_SKIP_OLLAMA=0 pytest -v
```

### Test Coverage

- **793 tests pass** (excluding 3 LLM-provider test-expectation drift failures and E2E/browser tests)
- 37 test files across `tests/integration/`, `tests/security/`, and `tests/e2e/`
- Tests cover: authentication, RBAC, advisory pipeline, approval gate, task workflow, audit logging, viewer redaction, MCP tool calls, LLM provider selection, prompt injection, and UI consistency.

### Evaluation Tasks

See [EVALS.md](EVALS.md) for 14 evaluation tasks with pass/fail results and one documented unresolved failure (Qwen2.5-3B drops citations on long multi-cluster prompts).

### Known Test Failures

Three tests in `tests/integration/test_llm_provider.py` fail due to test-expectation drift (the default model changed from `openrouter/free` to `qwen/qwen-2.5-7b-instruct`). These are test assertion issues, not production code defects. The production code correctly uses the current default model.

---

## Limitations

- **Local Ollama inference**: The implementation is complete and the fallback path is tested, but a successful end-to-end local run on suitable hardware is documented as unverified in EVALS.md Task 13. OpenRouter hosted inference (using the same open-weights model) is the developer's primary execution path.
- **Task 6 (conflicting weather sources)**: The fallback template does not explicitly cross-check conflicting weather signals; documented as PARTIAL in EVALS.md.
- **Best-effort audit logging**: `log_audit_event` catches its own exceptions (never raises to the caller). A successful state change could theoretically occur without an audit record if the audit write fails internally.
- **Synthetic data only**: All household, plot, weather, pest, and market data is synthetic. No real farmer records are used.
- **No automated farmer communication**: The system never sends SMS, USSD, or any message to farmers. The officer decides the delivery channel.
- **KALRO guidance permission-pending**: Crop-calendar material from KALRO is not yet authorised for operational use.

---

## Future Improvements

*These are proposed enhancements, not existing functionality.*

- Better coverage of locally verified agricultural evidence (consented data feeds, real crop calendars)
- Improved offline or low-connectivity support (USSD delivery, local caching)
- Additional evaluation using appropriately consented and validated field data
- Improved monitoring of tool failures and workflow reliability
- Stronger audit consistency (transaction-wrapped audit writes for all state changes)
- Expanded geographic and field-follow-up capabilities (turn-by-turn directions, offline maps)
- Additional language support (Swahili, Dholuo) and accessibility improvements
- Citation verification post-pass for smaller models that drop evidence references

---

## Licence, Security, and Responsible Use

### Licence

MIT — see [LICENSE](LICENSE). This is an OSI-approved licence.

### Security

- **Never commit `.env` files, passwords, API keys, or tokens.** The `.gitignore` covers `.env` and `.env.local`.
- API keys are read from environment variables and never logged.
- CSRF protection on all POSTs; HTTPS enforced in production (`config/settings/production.py`).
- Role-based access control enforced server-side via application-role checks, not Django's `is_staff` flag.
- Account approval workflow: registration creates PENDING accounts; `AccountStatusMiddleware` flushes sessions for non-approved users.
- Viewer data minimisation: officer names redacted to role labels; field-finding content excluded server-side.

### Responsible Use

- AI-generated drafts are **not** approved recommendations. They are starting points for professional review.
- The system does not verify real-world facts. Weather data does not confirm local field conditions. Missing pest reports do not prove pests are absent.
- Human officers remain responsible for all decisions communicated to farmers.
- The demonstration uses synthetic data, not real farmer household records.

---

## Contributing

Issues and pull requests welcome. All contributions must keep the human-in-the-loop invariant: no automated outbound messages, no auto-approval, no auto-task creation.

---

## Documentation Map

- [ARCHITECTURE.md](ARCHITECTURE.md) — one-page architecture overview
- [EVALS.md](EVALS.md) — 14 evaluation tasks with results and 1 unresolved failure
- [Architecture diagram (PDF)](docs/architecture/kachieng_ai_agent_architecture.pdf) — landscape architecture diagram
- [Architecture diagram (PNG)](docs/architecture/kachieng_ai_agent_architecture.png) — high-resolution image
- [docs/governance/human_approval_policy.md](docs/governance/human_approval_policy.md) — human approval gate policy
- [docs/governance/synthetic_data_notice.md](docs/governance/synthetic_data_notice.md) — synthetic data statement
- [docs/operations/developer_setup.md](docs/operations/developer_setup.md) — detailed developer setup guide
- [docs/operations/demo_script.md](docs/operations/demo_script.md) — demo video script
- [docs/operations/readiness_register.md](docs/operations/readiness_register.md) — production readiness register
- [docs/operations/capability_matrix.md](docs/operations/capability_matrix.md) — 7-capability audit with evidence
