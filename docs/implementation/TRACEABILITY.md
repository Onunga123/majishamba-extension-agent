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

## Phase 1 completion — endpoints 1 & 2 (health, clusters)

The roadmap's nine-endpoint contract (§A1 Table 2) numbers health and clusters
as endpoints 1 and 2. The initial Phase 1 cut built the token machinery and
endpoints 3–5; this step closes the gap so Phase 3's acceptance criteria (which
call `GET /api/v1/health/` and `GET /api/v1/clusters/`) have live targets.

| requirement | artifact |
| --- | --- |
| Endpoint 1 `GET /health/` (no auth, reuses `HealthCheckView`) | `apps/api/urls.py` — `path("health/", HealthCheckView.as_view(), ...)` |
| Endpoint 2 `GET /clusters/` (token: any active) | `apps/api/views.py` — `clusters_list_view`; `apps/api/urls.py` — `path("clusters/", ...)` |
| "token (any active)" auth path (no scope, no role gate) | `apps/api/auth.py` — `any_active_token_required` |
| Page-based pagination (default 25, ceiling 100) | `apps/api/views.py` — `_parse_int`, `_page_url`, `clusters_list_view` |
| `?q` filter on cluster_id / name / locality | `apps/api/views.py` — `clusters_list_view` (mirrors the HTML `q` filter) |
| Response fields per roadmap §A4 (7 fields) | `apps/api/views.py` — `clusters_list_view` result dict |
| Flat response shape (no `{"ok","data"}` envelope) | `docs/implementation/03_endpoints.md` — response-shape note |
| Tests | `tests/integration/test_api.py` — 11 new tests (3 health, 8 clusters) |

## Phase 3 — Base44 integration

Phase 3 is Base44-side work (roadmap §11, Phase 3): *"Base44 project (outside
this repo); Render dashboard; no Kachieng' repository changes beyond
environment."* This repo's Phase 3 contribution is the authoritative hand-off
(contract + reference client) and the API-side acceptance validation proving
the flow the Base44 Superagent drives actually works.

| requirement | artifact |
| --- | --- |
| Authoritative Base44 integration contract (real API + §A4 deviation table) | `docs/implementation/09_phase3_base44_integration.md` |
| Reference Deno client (types / apiClient / superagent + README) | `docs/implementation/base44_reference/` |
| Phase 3 acceptance — full Superagent flow (health → clusters → request → poll → detail) | `tests/integration/test_phase3_superagent_flow.py` — `test_phase3_superagent_flow_health_clusters_request_poll_display` |
| Phase 3 acceptance — "second human (supervisor) is configurable" | `tests/integration/test_phase3_superagent_flow.py` — `test_phase3_flow_second_human_supervisor_configurable` |
| Demo token provisioning (officer + supervisor) | `scripts/provision_base44_tokens.{ps1,sh}` |
| Render env notes (`MAJISHAMBA_SYNC_RUN=1`, `gunicorn --timeout 180`, `USE_POSTGRES=1`) | `docs/implementation/09_phase3_base44_integration.md` → "Render environment" |
| Decision: align API to §A4 vs. document the real contract | `docs/implementation/09_phase3_base44_integration.md` → deviation table + decision note (chose: document) |
