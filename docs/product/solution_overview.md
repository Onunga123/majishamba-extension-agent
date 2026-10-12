# Solution overview — Kachieng AI Agent

## In one paragraph

Kachieng AI Agent is a Django + LangGraph system with a custom MCP server (`majishamba-extension-mcp`) of eight tools. A Nyatike extension officer requests an advisory for a Kachieng cluster. A LangGraph agent calls the tools in order, drafts an advisory with the explicitly selected OpenRouter or Ollama provider (or a deterministic fallback), validates the output against a strict Pydantic schema, saves it as DRAFT, and stops. The officer reviews the DRAFT in the Django UI, approves / rejects / defers / requests-evidence. Only after approval can a follow-up task (field visit, cluster meeting, etc.) be created — enforced in code by an approval-gated action tool. The agent never sends SMS, places orders, or issues credit flags. The officer decides delivery.

## Components

### 1. Custom MCP server (`majishamba-extension-mcp`)

Eight tools in `apps/mcp_tools/tools.py`, registered in `TOOL_REGISTRY`. Two are action tools; one is approval-gated. The server is exposed via FastMCP from the official MCP Python SDK over stdio, AND called in-process by the agent and the Django UI. One code path per tool, three call sites.

### 2. Borrowed MCP server

The official filesystem MCP server, restricted to `docs/calendars/`, used in development for loading approved crop-calendar PDFs. Justification in `ARCHITECTURE.md`. Not exposed in production.

### 3. LangGraph agent (`apps/agents/graph.py`)

11 nodes: `validate_request` → `fetch_plot_history` → `fetch_crop_calendar` → `fetch_weather` → `fetch_pest_alerts` → `fetch_market_prices` → `validate_evidence` → `draft_advisory` → `validate_output_schema` → `save_draft` → `officer_approval_gate`. Conditional edges for errors (missing data, stale sources, conflicting weather signals, model-output invalidity, model unavailable).

### 4. Open-weights model

`draft_advisory` calls the provider selected by `LLM_PROVIDER` with a strict JSON-only prompt. `Advisory.generation_mode` records `llm_openrouter`, `llm_ollama`, or `fallback_template`; provider failures never silently switch models.

### 5. Approval gate

`apps/approvals/views.ApprovalGateView` is the only path that creates `OfficerApproval` rows. The action tool `create_follow_up_task_after_approval` calls `apps.tasks.service.create_follow_up_task_after_approval`, which checks `OfficerApproval(decision=APPROVED)` before creating a `FollowUpTask`. The gate cannot be bypassed.

### 6. Audit log

Every tool call, every HTTP mutation, every agent run start/end, every approval writes an `AuditEvent` row in `apps/audit`. The dashboard's audit view (`/dashboard/audit/`) shows the trail.

### 7. Django + HTMX UI

Django templates with Tailwind (CDN for the demo) and MapLibre GL JS for the cluster map. Server-rendered, minimal JS. The officer's workflow is: log in → dashboard → request advisory → review draft → approve → optional follow-up task → audit trail.

## What the agent does NOT do

- Send SMS or USSD messages.
- Place orders.
- Issue credit flags.
- Auto-approve advisories.
- Auto-create follow-up tasks.
- Call external HTTP APIs in the demo (the demo reads from synthetic fixtures; a real pilot would replace the tool implementations with live KMD/KALRO/market calls under the same Pydantic schemas).

## Why this design

- **Django** gives us ORM, admin, auth, migrations — the boring infrastructure that an institutional pilot needs.
- **LangGraph** gives us named nodes, typed state, conditional edges, and a natural place to stop for a human gate. A custom state machine would have re-implemented the same primitives.
- **MCP** gives us a single, observable tool interface that any client (the agent, the UI, an external MCP client) can call with identical behaviour.
- **OpenRouter or Qwen2.5-7B-Instruct via Ollama** provides a cloud demo path or local open-weights path respectively; only the verified local path supports a claim that the project ran downloaded open weights itself.
- **Pydantic schemas** give us strict validation on every tool input and on the model's JSON output. Invalid outputs are rejected and the agent falls back to the deterministic template.
- **HTMX** keeps the UI server-rendered, which is what an institutional IT department can deploy and maintain.
- **MapLibre GL JS** (no API key) gives us a free, open-source interactive map for the cluster view.
