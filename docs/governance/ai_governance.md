# AI governance — MajiShamba Extension Agent

## Principle

> **Agent recommends; human decides.**

The agent gathers evidence, drafts a structured advisory, validates the output, and saves a DRAFT. A named Nyatike extension officer reviews and approves before any advisory is recorded as APPROVED, and before any follow-up task is created. The agent never sends advice, places orders, or issues credit flags.

## What the agent is allowed to do

- Call read-only MCP tools to gather evidence (plot history, crop calendar, weather, pest alerts, market prices, evidence validation).
- Draft an advisory using Qwen2.5-7B-Instruct via Ollama, or fall back to a deterministic template.
- Validate its own draft against a strict Pydantic schema.
- Persist a DRAFT advisory record (`Advisory.status="draft"`).
- Stop and wait for human approval.

## What the agent is NOT allowed to do

- Send SMS, USSD, WhatsApp messages, emails, or any other outbound communication.
- Place orders for inputs (seed, fertilizer, pesticide).
- Issue credit flags or recommend specific credit products.
- Approve its own advisory.
- Create a follow-up task without a valid `OfficerApproval(decision=APPROVED)` row.
- Modify an APPROVED advisory.
- Modify its own audit log.
- Override the officer's decision.

## Enforcement in code

| Rule | Where enforced |
|---|---|
| Agent cannot send messages | `apps/agents/graph.py` does not import `requests.post`, `twilio`, `africastalking`, `send_mail`, or any SMS/HTTP-send helper. Verified by `tests/security/test_security.py::test_no_external_message_can_be_sent_by_agent`. |
| Agent cannot approve its own advisory | `apps/approvals/views.ApprovalGateView` is the only path that creates `OfficerApproval` rows; it requires `user.can_approve()`. |
| Agent cannot create a task without approval | `apps/tasks/service.py:create_follow_up_task_after_approval` checks `OfficerApproval(decision=APPROVED)` for the (advisory, officer) pair. Wrapped in `@transaction.atomic`. Tested in `tests/security/test_security.py::test_follow_up_task_service_enforces_approval_gate`. |
| Viewer cannot approve | `apps/accounts/permissions.ApproverRequiredMixin` denies viewers. Tested in `tests/security/test_security.py::test_viewer_cannot_approve`. |
| Anonymous cannot request | `apps/accounts/permissions.OfficerRequiredMixin` redirects to login. |
| Inputs are validated | Pydantic schemas in `apps/agents/schemas.py` for every tool. |
| Outputs are validated | `AdvisoryDraft` Pydantic schema in `apps/agents/schemas.py`. |
| Prompt injection is mitigated | `_sanitize_inputs` strips prompt-injection phrases; the agent prompt does not embed raw evidence text. |
| Audit log is immutable for the agent | `AuditEvent` rows are created by `apps.audit.service.log_*` functions only; the agent does not write to `AuditEvent` directly. |

## Open-weights model

- **Model.** Qwen2.5-7B-Instruct.
- **Runtime.** Ollama, local (no third-party API).
- **Fallback.** Deterministic template generator when the model is unavailable or output is invalid.
- **Provenance.** `Advisory.generation_mode` records `ollama_qwen` or `fallback_template`. `Advisory.model_name`, `model_run_id`, `model_prompt_hash` are stored on each Advisory row.
- **No household/plot data leaves the local machine.** The model is invoked locally; the prompt contains synthetic household/plot data and aggregate weather/pest/market signals.

## Synthetic data conduct

- All household and plot records are **synthetic**. See `docs/governance/synthetic_data_notice.md`.
- Aggregate weather/pest/market signals are synthetic summaries inspired by publicly-known sources.
- No real Nyatike household data is used in the demo or in tests.

## Reproducibility

- All fixtures are versioned in `data/fixtures/`.
- All tool calls are logged to `AuditEvent`.
- All agent runs write `agent_run:start` and `agent_run:end` audit events.
- `make test` reproduces the test suite.

## Security scans

- `pip-audit` (Python deps)
- `Semgrep CE` (code patterns)
- `gitleaks` (secrets — install separately; documented in Makefile)
- Ruff / Black / mypy (style + types)

Run `make security` to execute them.

## Incident response

In a real pilot, a rejected advisory or a blocked task-creation attempt is visible in the audit log immediately. The officer's supervisor (a separate role in `apps.accounts`) can review the audit trail at `/dashboard/audit/` or `/audit/`. Any deviation from the rules above is a bug; file an issue and disable the offending tool in `TOOL_REGISTRY` until it's fixed.
