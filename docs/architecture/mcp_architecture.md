# MCP architecture — MajiShamba Extension Agent

## Custom server: `majishamba-extension-mcp`

**Code.** `apps/mcp_tools/tools.py` (tool implementations) and `apps/mcp_tools/server.py` (FastMCP wrapper).

**SDK.** Official MCP Python SDK (`mcp.server.fastmcp.FastMCP`). Falls back to a JSON-RPC-over-stdio shim if the SDK is missing (`_json_rpc_stdio_shim`).

**Transport.** stdio.

**Tools (8).** All defined in `TOOL_REGISTRY` and called from three places with identical behaviour:

| # | Tool | Type | Approval gate |
|---|---|---|---|
| 1 | `get_cluster_plot_history` | read | — |
| 2 | `get_crop_calendar` | read | — |
| 3 | `get_weather_and_rainfall_context` | read | — |
| 4 | `get_pest_alerts` | read | — |
| 5 | `get_market_price_context` | read | — |
| 6 | `validate_advisory_evidence` | read | — |
| 7 | `create_draft_advisory_record` | **action** | none (only DRAFT is created; no message sent) |
| 8 | `create_follow_up_task_after_approval` | **action** | **approval-gated** — must find `OfficerApproval(decision=APPROVED)` |

## Logging contract

Every tool call writes an `AuditEvent` row via `apps.audit.service.log_tool_call`:

```json
{
  "tool_name": "get_cluster_plot_history",
  "inputs_summary": {"value": "<sanitised inputs truncated to 800 chars>"},
  "outputs_summary": {"value": "<sanitised outputs truncated to 800 chars>"},
  "approval_status": "draft | approved | blocked | rejected | ''",
  "actor_id": <user id or null>,
  "metadata": {"ts": "<iso8601>"}
}
```

Sanitisation (`_sanitize_inputs`):
- Strips prompt-injection phrases (`ignore`, `disregard`, `forget`, `new instructions`, `system prompt`) — replaces with `[redacted]`.
- Strips secrets (`password`, `secret`, `token`, `api_key`) — replaces with `<marker redacted>…`.

## Approval gate (action tool 8)

```python
def create_follow_up_task_after_approval(*, approved_advisory_id, officer_id, task_type, deadline=None, ward="Kachieng", actor=None):
    advisory = Advisory.objects.get(pk=approved_advisory_id)
    approval = OfficerApproval.objects.filter(
        advisory_id=advisory.id,
        officer_id=officer_id,
        decision=OfficerApproval.Decision.APPROVED,
    ).order_by("-created_at").first()
    if not approval:
        return {"error": "Approval gate: no APPROVED OfficerApproval record for this advisory/officer."}
    if advisory.status != Advisory.Status.APPROVED:
        return {"error": f"Advisory status is {advisory.status}, not APPROVED."}
    task = FollowUpTask.objects.create(approved_advisory=advisory, owner_id=officer_id, task_type=task_type, deadline=deadline, ward=ward)
    log_audit_event(actor=actor, action="create_follow_up_task", target=task, metadata={...})
    return {"task_id": task.id, "status": task.status, "advisory_id": advisory.id}
```

Two independent checks must pass before any `FollowUpTask` is created. The function is wrapped in `@transaction.atomic` so a failure rolls back.

## Borrowed server: official filesystem MCP server

Used only in development. Restricted to `docs/calendars/` via `MAJISHAMBA_BORROWED_FILESYSTEM_MCP_ROOT`.

Justification (also in `ARCHITECTURE.md`):

> We use the official filesystem MCP server to load approved crop-calendar documents during development because it provides safe, tested file access without building a custom document loader.

The custom agent does not depend on this server for the demo — the demo reads calendars from the database via `get_crop_calendar`. The borrowed server exists to satisfy the "borrowed MCP server" requirement and to demonstrate MCP craft alongside the custom server.

## Why MCP (not just functions)

The custom MCP server is the **contract surface**. Tools can be invoked by:

1. The LangGraph agent (in-process via direct import).
2. The Django UI (in-process via direct import).
3. External MCP clients (stdio via FastMCP).

All three call the same `TOOL_REGISTRY` function. There is one code path per tool. This means:

- The agent and the UI never disagree on what a tool does.
- An external MCP client (e.g. a partner agent from another lab) can call `get_cluster_plot_history` and get the same answer as the in-process agent.
- Tests can exercise a tool directly without spinning up an MCP transport.

## Schema contract

Tool inputs are validated by Pydantic schemas in `apps/agents/schemas.py`. The schemas are shared between the MCP server, the agent, and the Django UI. A change to a schema is visible in all three places — there is no separate "MCP schema file" that can drift.

## Failure modes

| Failure | Behaviour |
|---|---|
| Tool raises an exception | Caught by the runner; agent records an error in `state.errors` and routes to `officer_approval_gate` (terminal) |
| Approval gate fails | Tool returns `{"error": "Approval gate: ..."}`; no task is created; audit event logs `approval_status="blocked"` |
| Model output fails Pydantic validation | Agent retries `draft_advisory` once with the template; if the template also fails, routes to terminal |
| Ollama unreachable | `draft_advisory` falls back to the template; `generation_mode="fallback_template"` on the Advisory record |
| Stale crop calendar | `get_crop_calendar` returns `is_stale=true` and a warning; `validate_output_schema` downgrades `confidence` to `low` |
| Prompt-injection text in tool inputs | `_sanitize_inputs` strips it; the text never reaches the model in raw form |
