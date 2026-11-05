# Phase 1 traceability register

Maps each requirement of the Base44-API phase to the artifact that fulfils it.

## Phase 0 — setup & methodology

| requirement | artifact |
| --- | --- |
| Branch from `26309cf` (origin/main) | `feature/base44-api` (branched after `git fetch`) |
| Clean worktree | mode-only mods discarded; `majishamba_fresh` worktree clean |
| Baseline test run recorded | `TEST_AND_VALIDATION_LOG.md` |
| Project orientation doc | `PROJECT_CONTEXT.md` |
| Implementation memory docs (8) | `docs/implementation/00_overview.md` … `07_rollout_and_rollback.md` |
| Traceability register | this file |

## Phase 1 — API implementation

| requirement | artifact |
| --- | --- |
| `apps/api` app structure | `apps/api/{__init__,apps,models,auth,views,urls}.py`, `apps/api/management/commands/generate_api_token.py` |
| `ApiToken` model: hashed SHA-256 | `apps/api/models.py` — `hash_token()`, `token_hash`, `create_token()` |
| … scoped | `apps/api/models.py` — `Scope` enum, `scopes` JSONField, `has_scope()` |
| … expiring | `apps/api/models.py` — `expires_at`, `is_active` |
| … revocable | `apps/api/models.py` — `revoked_at`, `revoke()` |
| migration | `apps/api/migrations/0001_initial.py` |
| `token_required` + `csrf_exempt` decorator | `apps/api/auth.py` |
| eligibility re-check per scope | `apps/api/auth.py` — `_SCOPE_ELIGIBILITY` map |
| Extract `request_advisory_run()` | `apps/advisories/services.py` |
| Refactor `RequestAdvisoryView` to call it | `apps/advisories/views.py` (`RequestAdvisoryView.post`) |
| Extract `record_approval()` | `apps/approvals/services.py` |
| Refactor `ApprovalGateView` to call it | `apps/approvals/views.py` (`ApprovalGateView.post`) |
| API views: advisory request, approval, introspect, revoke | `apps/api/views.py` |
| Wire `/api/v1/` | `apps/api/urls.py`, `config/urls.py` |
| `generate_api_token` command | `apps/api/management/commands/generate_api_token.py` |
| Settings: INSTALLED_APPS | `config/settings/base.py` (`apps.api` added) |
| Settings: token config | `config/settings/base.py` (`MAJISHAMBA` dict) |
| Settings: ALLOWED_HOSTS note | `docs/implementation/05_settings_and_security.md` |
| Tests | `tests/integration/test_api.py` (26 tests) |

## Security hardening done alongside

| item | artifact |
| --- | --- |
| Remove leaked credential from parent clone's remote URL | parent repo `origin` rewritten to clean `https://github.com/...` URL |
| Push using a throwaway `http.extraheader` (no persistence, no echo) | push step (end of phase) |

## Phase 2 — Advisory integration

Maps the Phase 2 requirements (roadmap §11, Phase 2) to the artifacts that
fulfil them.

| requirement | artifact |
| --- | --- |
| Extract `request_advisory_run` with `@transaction.atomic` + `select_for_update` (TOCTOU) | `apps/advisories/services.py` — `request_advisory_run` (locks the `FarmerCluster` row) |
| Endpoint 3 `POST /advisories/` (canonical path) | `apps/api/urls.py` — `path("advisories/", ...)`; `apps/api/views.py` — `request_advisory_view` |
| Back-compat alias `POST /advisories/request/` | `apps/api/urls.py` — `path("advisories/request/", ...)` (same view) |
| Endpoint 4 `GET /runs/<uuid>/` (run-status polling) | `apps/api/views.py` — `run_status_view`; `apps/api/urls.py` — `path("runs/<uuid:run_id>/", ...)` |
| Endpoint 5 `GET /advisories/<pk>/` (advisory detail + evidence) | `apps/api/views.py` — `advisory_detail_view`; `apps/api/urls.py` — `path("advisories/<int:advisory_pk>/", ...)` |
| `advisories:read` scope + eligibility (officer / system admin) | `apps/api/models.py` — `Scope.ADVISORIES_READ`; `apps/api/auth.py` — `_SCOPE_ELIGIBILITY` |
| Run-status access rule (owner / officer / sysadmin) | `apps/api/views.py` — `run_status_view` (mirrors web `AdvisoryRunStatusView`) |
| Soft-deleted advisories hidden from the API | `apps/api/views.py` — `advisory_detail_view` uses `Advisory.objects` (active manager) |
| `FAILED` recorded on a pipeline exception | `apps/agents/run_worker.py` — `execute_advisory_run` try/except |
| `AuditEvent.actor` equals the token user | `apps/api/views.py` — `request_advisory_view` logs `advisory:request` with `actor=request.user` |
| Phase 2 tests | `tests/integration/test_api.py` — 9 new tests |
