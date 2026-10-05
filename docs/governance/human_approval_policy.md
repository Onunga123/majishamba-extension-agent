# Human approval policy — MajiShamba Extension Agent

## Why human approval is required

The Nyatike Sub-County Agricultural Office serves smallholder farmers in Kachieng Ward. Planting advisories influence household decisions about seed, fertilizer, labour and timing — decisions with real cost consequences when rainfall onset is erratic and fall armyworm is active. An automated agent that sent advisories directly to farmers could:

- Cause premature planting on a false rainfall start (replanting costs).
- Cause panic pesticide use from a prompt-injection in a pest alert.
- Issue inappropriate marketing advice that farmers might act on.
- Create unreviewed follow-up tasks that consume officer time without officer consent.
- Erode trust between farmers and the office.

The principle is **agent recommends; human decides**. The agent's job is to gather evidence and produce a defensible draft. The officer's job is to approve, edit, reject, defer, or request more evidence, and to decide how to communicate the result to farmers.

## How it is enforced in code

### 1. The DRAFT gate

The agent's `save_draft` node calls `apps.mcp_tools.tools.create_draft_advisory_record`, which creates an `Advisory` row with `status="DRAFT"`. No APPROVED record is created by the agent. The agent then routes to `officer_approval_gate` and stops.

### 2. The approval view

`apps/approvals/views.ApprovalGateView` is the **only** code path that creates `OfficerApproval` rows. The view:

- Requires `user.can_approve()` (extension officer or supervisor role).
- Creates an `OfficerApproval` row with `decision` ∈ {approved, rejected, deferred, needs_evidence}.
- Updates `Advisory.status` accordingly.
- Logs an `AuditEvent(action="officer_approval")`.

### 3. The task-creation gate

`apps/tasks/service.create_follow_up_task_after_approval` is the **only** function that creates `FollowUpTask` rows. It:

- Looks up `OfficerApproval.objects.filter(advisory_id=..., officer_id=..., decision="approved").first()`.
- If no such approval exists, returns `{"error": "Approval gate: ..."}` and creates no task.
- If the advisory status is not `APPROVED`, also returns an error.
- Otherwise, creates the `FollowUpTask` and logs an `AuditEvent(action="create_follow_up_task")`.

The function is wrapped in `@transaction.atomic`, so any failure rolls back.

The MCP action tool `create_follow_up_task_after_approval` calls this function. External MCP clients (Claude Desktop, a partner agent) also call this function — the gate applies to them too.

### 4. The viewer guard

A viewer (`User.role="viewer"`) cannot:
- Request an advisory (`apps.advisories.views.RequestAdvisoryView` requires `user.is_officer()`).
- Approve an advisory (`apps.approvals.views.ApprovalGateView` requires `user.can_approve()`).
- Edit a DRAFT (`apps.advisories.views.AdvisoryEditView` requires `user.is_officer()`).

### 5. The audit log

Every approval decision and every task-creation attempt is logged to `AuditEvent` with the officer's id, the decision, and a truncated comment. The audit trail is visible at `/dashboard/audit/` and `/audit/`.

## What the agent is not allowed to do

- Send SMS / USSD / WhatsApp / email.
- Place orders for inputs.
- Issue credit flags.
- Approve its own advisory.
- Create a follow-up task without an APPROVED `OfficerApproval` row.
- Modify an APPROVED advisory.
- Modify the audit log.

## What the officer is not allowed to skip

- The Pydantic schema validation on the draft (it always runs).
- The approval gate (no `--force-approve` flag exists).
- The audit log (it is written automatically by `log_audit_event`).

## What the supervisor can do that the officer cannot

- Nothing in the current build. The supervisor role is the same as the extension officer for the purposes of this MVP, except that supervisors are expected to spot-check the audit trail. A real pilot might restrict task creation to supervisors, but that is out of scope for this build.

## Edge cases

- **Officer edits the draft, then approves.** Allowed. The edit view (`apps.advisories.views.AdvisoryEditView`) updates the DRAFT body / summary / limitations / recommendation_type. The approval view then approves the edited draft.
- **Officer defers.** `Advisory.status="DEFERRED"`. The officer can re-evaluate later; the agent is not re-run automatically.
- **Officer requests more evidence.** `Advisory.status="NEEDS_EVIDENCE"`. The officer is expected to fix the data (e.g. collect missing plot records) and then re-request the advisory. No automatic re-run.
- **Officer rejects.** `Advisory.status="REJECTED"`. The draft is preserved in the audit log; a new advisory can be requested later.

## Pilot expansion (out of scope)

A real pilot might add:
- Two-person rule for approvals (officer proposes, supervisor approves).
- Time-limited approvals (auto-expire after N days).
- Approval templates (e.g. "approve with minor edits only").
- <!-- OUT OF SCOPE FOR MVP: SMS notification to the officer when a DRAFT is ready.
     The MVP intentionally does NOT send any outbound messages — the officer
     must visit the dashboard to discover DRAFTs. This is a deliberate design
     choice to keep the human-in-the-loop invariant strict. -->

These are out of scope for the challenge build but the code structure (a single `OfficerApproval` table, a single approval view, a single audit log) supports them.
