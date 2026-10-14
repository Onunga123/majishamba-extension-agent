# ARCHITECTURE — Kachieng AI Agent

## Agent shape (LangGraph)

```mermaid
flowchart TD
  START([START]) --> validate_request
  validate_request -->|errors| officer_approval_gate
  validate_request -->|ok| fetch_plot_history
  fetch_plot_history --> fetch_crop_calendar
  fetch_crop_calendar --> load_calendar_from_borrowed_mcp
  load_calendar_from_borrowed_mcp --> fetch_weather
  fetch_weather --> fetch_pest_alerts
  fetch_pest_alerts --> fetch_market_prices
  fetch_market_prices --> validate_evidence
  validate_evidence --> draft_advisory
  draft_advisory --> validate_output_schema
  validate_output_schema -->|invalid| use_fallback_template
  validate_output_schema -->|valid| save_draft
  use_fallback_template --> validate_output_schema
  save_draft --> officer_approval_gate
  officer_approval_gate --> END([END — officer reviews in Django UI])
```

The graph is built in `apps/agents/graph.py` with `langgraph.graph.StateGraph`. State is the `AgentState` TypedDict (`apps/agents/state.py`). Each node is a plain function that returns a dict patch. Conditional edges route on errors (missing data, stale sources, model-output invalidity, model unavailable).

**`load_calendar_from_borrowed_mcp`** is the node that exercises the **borrowed** official filesystem MCP server. It reads `docs/calendars/sample_calendar.txt` (either directly for the dev default, or via `npx @modelcontextprotocol/server-filesystem` if `MAJISHAMBA_BORROWED_MCP_USE_NPX=1`) and logs the call to `AuditEvent(tool_name="borrowed_filesystem_mcp")`.

**Validation-retry behaviour.** If `validate_output_schema` finds errors, it routes to the `use_fallback_template` node — **not** back to `draft_advisory`. Re-calling a non-deterministic model on a structural validation failure is wasteful and unlikely to fix the issue. The fallback template produces guaranteed-valid JSON, which re-validates and proceeds to `save_draft`.

After `officer_approval_gate` the agent stops. Approval happens **outside** the graph, in the Django UI (`apps/approvals/views.py`). Only after the officer approves does the system call `apps.tasks.service.create_follow_up_task_after_approval`, which is the same function the MCP action tool wraps.

## AI model and deployment modes

The `draft_advisory` node calls the provider selected by the `LLM_PROVIDER` environment variable (`apps/agents/llm_provider.py`). Three modes are supported:

| Mode | `LLM_PROVIDER` | Default model | What happens |
|------|-----------------|---------------|--------------|
| Hosted (cloud) | `openrouter` | `qwen/qwen-2.5-7b-instruct` | One HTTP request to OpenRouter's chat-completions endpoint (`https://openrouter.ai/api/v1/chat/completions`). Requires `OPENROUTER_API_KEY`. |
| Local (open-weights) | `ollama` | `qwen2.5:7b-instruct` | One call to the local Ollama server (`ollama.Client.generate`). Requires Ollama installed and the model pulled. |
| Fallback (no model) | `none` | N/A | No model inference. A deterministic template builds the advisory from collected evidence. |

**The code default is `none`** — if `LLM_PROVIDER` is not set, no model is invoked. The `.env.example` file configures `LLM_PROVIDER=openrouter` so that copying `.env.example` to `.env` enables hosted inference by default. Tests force `LLM_PROVIDER=none` via `tests/conftest.py` to avoid real API calls.

**Hosted inference (OpenRouter)** lets the application run on a machine that cannot practically run a 7B model locally. The developer's machine sends a prompt to OpenRouter's cloud API; the model runs on OpenRouter's infrastructure. The returned model identifier is recorded in `Advisory.model_name` and `generation_mode` is set to `llm_openrouter`.

**Local inference (Ollama)** preserves the local open-weights execution path. The developer's machine runs Qwen 2.5 7B Instruct via Ollama. Subject to the user's hardware (sufficient RAM/VRAM to load the 7B model). The implementation exists and is tested for failure handling (EVALS.md Task 10 — fallback when Ollama is unavailable), but a successful end-to-end local run remains unverified in the audit environment (EVALS.md Task 13 — marked 🟡 UNVERIFIED). The README documents this as a supported option for users with suitable hardware.

All model output is fenced-stripped, JSON-parsed, and validated against `AdvisoryDraft` (Pydantic). A provider failure never silently switches provider or model: it is recorded in metadata and the graph uses the deterministic template. `Advisory.generation_mode` records `llm_openrouter`, `llm_ollama`, or `fallback_template`.

**Timeouts.** Dev default: 10 seconds (fast failure → fallback). Production default: 60 seconds. Override with `MAJISHAMBA_OLLAMA_TIMEOUT` (Ollama) or `OPENROUTER_TIMEOUT_SECONDS` (OpenRouter).

## Tool functions and MCP architecture

### Shared tool functions (not an MCP server)

Eight tool functions are defined in `apps/mcp_tools/tools.py` and registered in `TOOL_REGISTRY`. These are **ordinary Python functions** — not an MCP server. Six are read-only (`get_cluster_plot_history`, `get_crop_calendar`, `get_weather_and_rainfall_context`, `get_pest_alerts`, `get_market_price_context`, `validate_advisory_evidence`). Two are **action tools** (`create_draft_advisory_record`, `create_follow_up_task_after_approval`); the latter is **approval-gated** — it delegates to `apps/tasks/service.create_follow_up_task_after_approval` which checks `OfficerApproval(decision=APPROVED)`.

The same `TOOL_REGISTRY` functions are called from three places, ensuring identical behaviour:
1. The LangGraph agent (`apps/agents/graph.py`) — in-process.
2. The Django HTTP endpoint (`apps/mcp_tools/views.py`) — POST to `/mcp/tools/<name>/call/`.
3. The standalone MCP server (`apps/mcp_tools/server.py`) — stdio transport for external MCP-aware clients.

**Single logging path.** Each tool logs itself to `AuditEvent` via `log_tool_call` in `apps/audit/service.py`. The graph nodes do **not** add a second log entry. The `actor_id` (requesting officer's id) is propagated from the runner → state → every tool call, so every `AuditEvent` row is attributed to a named officer. Prompt-injection patterns are stripped from text fields by `_sanitize_inputs`.

### Custom MCP server: `majishamba-extension-mcp`

Built with the official **MCP Python SDK** (`mcp.server.fastmcp.FastMCP`) in `apps/mcp_tools/server.py`. It exposes the 8 tool functions over stdio to any MCP-aware client (Claude Desktop, a test harness, a partner agent). The server is intentionally thin — it delegates to the same `TOOL_REGISTRY` functions that the agent and Django views call. If the MCP SDK is not installed, a minimal JSON-RPC-over-stdio shim is used.

### Borrowed MCP server: official filesystem MCP server

The official `@modelcontextprotocol/server-filesystem` is used in the `load_calendar_from_borrowed_mcp` graph node to load approved crop-calendar documents from `docs/calendars/`. Restricted to that directory via `MAJISHAMBA_BORROWED_FILESYSTEM_MCP_ROOT`. Not exposed in production. The demo does not depend on it — calendars are loaded from the database via `get_crop_calendar`.

## Data flow

```text
Extension Officer (browser) ──HTMX──▶ Django view (apps/advisories/views.py)
                                          │
                                          ▼
                          apps/agents/runner.run_advisory_pipeline
                                          │
                                          ▼
                          LangGraph (apps/agents/graph.py)
                                          │
              ┌───────────────────────────┼─────────────────────────────┐
              ▼                           ▼                              ▼
   apps/mcp_tools/tools.*         LLM provider call             Pydantic validation
   (shared tool functions,         (OpenRouter / Ollama          (AdvisoryDraft schema)
    in-process)                    / fallback template)
              └───────────┬───────────────┴──────────────────────────────┘
                          ▼
                  apps/audit/service.log_tool_call   (every call)
                          ▼
                  Advisory(DRAFT)  →  Django UI  →  OfficerApproval(APPROVED)
                          ▼
                  apps/tasks.service.create_follow_up_task_after_approval  (gate)
                          ▼
                  FollowUpTask  (status=ASSIGNED)
```

## Approval gate design

The gate is **non-negotiable**:

- `create_draft_advisory_record` is an action tool, but it only persists a DRAFT. No external message is sent.
- `create_follow_up_task_after_approval` is an action tool that **must** find a valid `OfficerApproval(decision=APPROVED)` for the (advisory_id, officer_id) pair before creating a `FollowUpTask`. If the gate fails, the tool returns an error dict and **no task is created**.
- The Django view `apps/approvals/views.ApprovalGateView` is the only path that creates `OfficerApproval` rows. It requires `user.can_approve()` (extension officer or supervisor role).

## Why LangGraph (not custom)

LangGraph gives named nodes + typed state + conditional edges + the ability to stop at a human gate. A custom state machine would have re-implemented the same primitives. LangGraph is open-source, audit-friendly, and easy to read in `apps/agents/graph.py`.

## Why a custom MCP server (not just functions)

The custom MCP server is the contract surface. Tools can be invoked by the agent (in-process), by the Django UI (HTTP), and by external MCP clients (stdio) with **identical behaviour**. This is the point of MCP — a single, observable tool interface that any client can call.

## Why a borrowed filesystem MCP server

Approved crop-calendar documents already exist as files; building a custom document loader would be reinventing a tested, maintained tool. The official filesystem MCP server is restricted to `docs/calendars/` so it cannot leak arbitrary files.

## Security and governance

- **Role-based access control:** Extension Officer, Supervisor, Viewer, System Administrator. Application-role checks (`is_officer()`, `is_system_admin()`) — not Django's `is_staff` flag — gate MCP tool access, agent graph view, advisory run status, and audit visibility. `create_officer` no longer grants `is_staff=True` automatically.
- **Audit visibility:** The full audit log (`/audit/`, `/audit/export.csv`) is restricted to System Administrators (Phase B). The dashboard activity feed excludes account-management events for non-admins. Officer names are redacted for Viewers on task pages.
- **Profile access:** Profile page is GET-only and requires authentication (Phase C).
- **Task workflow enforcement:** Completion only from ASSIGNED or IN_PROGRESS; verification only from COMPLETED with at least one finding; findings only from ASSIGNED or IN_PROGRESS (Phase D, Priority 3). Task ownership alone does not bypass the `is_officer()` requirement.
- **MCP actor identity:** The HTTP MCP tool endpoint binds `actor`/`actor_id` to the authenticated request user; client-supplied values are stripped (Phase D, Priority 1). Action tools enforce `is_officer()` at the tool boundary. Follow-up task creation prevents officer impersonation.
- **Viewer data minimization:** Viewers cannot see field-finding content (observations, missing information, follow-up notes) on task detail pages; findings are excluded server-side (Phase D, Priority 2). Officer real names are redacted to role labels.
- **Account security:** Registration creates PENDING accounts with `is_active=False`. Pending accounts cannot log in. Session eligibility middleware flushes sessions for non-approved users.
- CSRF on all POSTs; HTTPS enforced in `production.py`; HSTS, HttpOnly sessions, SameSite=Lax.
- Pydantic validation on every MCP tool input (`apps/agents/schemas.py`) and on the model's JSON output (`AdvisoryDraft`).
- Structured JSON logging without secrets; `_sanitize_inputs` strips prompt-injection phrases.
- Audit log (`AuditEvent`) for every tool call, HTTP mutation, agent run start/end, and approval.

See [docs/governance/human_approval_policy.md](docs/governance/human_approval_policy.md) for the full approval-gate policy and [docs/governance/synthetic_data_notice.md](docs/governance/synthetic_data_notice.md) for the synthetic-data statement.
