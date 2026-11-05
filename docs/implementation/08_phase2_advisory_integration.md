# Phase 2 — Advisory integration

## Goal

Enable an external integration (for example an app built on the Base44 app
builder) to request an advisory run and retrieve its status and the generated
draft over `/api/v1/`, without holding a Django session. This is the roadmap's
Phase 2 (roadmap §11), building on the Phase 1 token infrastructure.

## In scope

- Endpoint 3 `POST /api/v1/advisories/` (canonical roadmap path; the existing
  `POST /api/v1/advisories/request/` is retained as a back-compat alias and
  maps to the same handler).
- Endpoint 4 `GET /api/v1/runs/<uuid>/` — run-status polling.
- Endpoint 5 `GET /api/v1/advisories/<pk>/` — advisory detail + evidence.
- A new `advisories:read` scope (eligibility: `is_officer()` or
  `is_system_admin()`).
- The TOCTOU fix on the shared `request_advisory_run` service
  (`@transaction.atomic` + `select_for_update` on the cluster row).
- `FAILED` recording on a pipeline exception in `execute_advisory_run`.
- `advisory:request` audit attribution to the token user.

## Deliberately out of scope (deferred)

- Rate limiting / per-token quotas — roadmap Phase 6 (production hardening),
  explicitly excluded from the pre-event critical path. Partial work from an
  earlier pass was saved to `scripts/phase6_rate_limiting.patch` for reuse.
- A read/list API for clusters or approvals — the clusters list is a Phase 1
  gap (roadmap endpoint 2); approvals history is Phase 4.
- OAuth / session-coupled auth.

## Files changed

- `apps/advisories/services.py` — `request_advisory_run` wrapped in
  `@transaction.atomic`; the `FarmerCluster` row is locked with
  `select_for_update` so two concurrent requests for the same cluster cannot
  both pass the dedup check.
- `apps/agents/run_worker.py` — `execute_advisory_run` catches pipeline
  exceptions and records a `FAILED` run with `error_message` instead of
  propagating to the caller.
- `apps/api/models.py` — new `Scope.ADVISORIES_READ = "advisories:read"`.
- `apps/api/auth.py` — `advisories:read` eligibility added to
  `_SCOPE_ELIGIBILITY`.
- `apps/api/views.py` — `run_status_view`, `advisory_detail_view`, and an
  `advisory:request` audit event in `request_advisory_view`.
- `apps/api/urls.py` — routes for endpoints 3 (canonical), 4, and 5.
- `tests/integration/test_api.py` — 9 new tests.

No migration is required: the new scope is a `Scope` enum value stored in the
existing `scopes` JSONField, so there is no schema change
(`makemigrations --check` reports "No changes detected").

## Acceptance criteria (roadmap Phase 2)

- POST returns `run_id` and `status`. ✅
- Polling reaches `COMPLETED` / `COMPLETED_WITH_FALLBACK` (sync run). ✅
  — `test_run_status_polls_to_completed`
- Advisory detail includes evidence and `content_version`. ✅
  — `test_advisory_detail_serializes_evidence_and_version`
- `AuditEvent.actor` equals the token user. ✅
  — `test_request_advisory_audit_attributes_to_token_user`
- Duplicate submission reuses the in-flight run (30-min guard). ✅
  — `test_request_advisory_dedup_reuses_run` (pre-existing)
- `FAILED` recorded on a pipeline exception. ✅
  — `test_run_status_failed_on_pipeline_exception`
- Soft-deleted advisories hidden. ✅
  — `test_advisory_detail_hides_soft_deleted`

## Estimate

Roadmap estimate 4–5h. The service extraction (`request_advisory_run`) was
already done in Phase 1, so this phase added the two read endpoints, the
canonical request path, the transaction safety, the failure handling, the
audit hook, and the test suite.
