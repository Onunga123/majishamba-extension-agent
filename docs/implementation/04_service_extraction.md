# Service extraction — `apps/advisories/services.py`, `apps/approvals/services.py`

## Why

Before this phase, the request-advisory and record-approval logic lived
inline in the web views (`RequestAdvisoryView.post`, `ApprovalGateView.post`).
Exposing the same actions over the API without duplicating that logic — and
risking the two paths diverging — required pulling the domain behaviour into
plain functions that both the web view and the API view call. The web views
now contain only HTTP concerns (form parsing, messages, redirects); the
services own the transactional domain work.

## `request_advisory_run(*, actor, cluster_id) -> AdvisoryRequestResult`

Located in `apps/advisories/services.py`. Extracted verbatim from the old
`RequestAdvisoryView.post`:

1. `require_officer(actor)` (raises `PermissionDenied`).
2. Look up the `FarmerCluster` by `cluster_id`; raise `ClusterNotFound` if
   missing (the web view maps this to a 404, the API to a JSON 404).
3. **30-minute dedup:** if an `AdvisoryRun` for the same officer+cluster
   exists in an in-flight status (`QUEUED/RUNNING/WAITING_FOR_MODEL/VALIDATING`)
   created within the last 30 minutes, reuse it (`created=False`).
4. Otherwise create a `QUEUED` run and call `start_advisory_run_async(run.pk)`.

Returns `AdvisoryRequestResult(run_id, status, created)`. The web view
redirects to `advisories:run_status`; the API returns the JSON envelope.

## `record_approval(*, actor, advisory_pk, decision, comments, content_version, create_followup, task_type, deadline) -> ApprovalResult`

Located in `apps/approvals/services.py`, decorated `@transaction.atomic`.
Extracted from the old `ApprovalGateView.post`:

1. `require_approver(actor)`.
2. Load the advisory (raise `AdvisoryNotFound`).
3. Reject if not `DRAFT` (`AdvisoryNotDraft`).
4. **Optimistic check:** `content_version` must match the advisory's current
   version (`VersionMismatch`).
5. **Pessimistic lock:** `select_for_update()` and re-check version + status
   under the row lock, so two concurrent approvals cannot both succeed against
   the same version.
6. Create the `OfficerApproval` row, advance the advisory status per the
   decision, save.
7. `log_audit_event(...)` with the same metadata the old view used.
8. If `decision == APPROVED` and `create_followup`, call
   `create_follow_up_task_after_approval`; capture `followup_task_id` or, on
   failure, `followup_error` (preserving the old view's "Could not create task"
   message).

Returns `ApprovalResult(advisory_id, status, approval_id, followup_task_id, followup_error)`.

## Behaviour preservation

The refactored web views produce the same messages, redirects, and audit
records as before. This is verified by `test_web_request_advisory_still_redirects_to_run`
and `test_web_approval_gate_still_records_approval`. The full pre-existing
suite (799 passing at baseline) continues to pass unchanged.
