# Test & Validation Log

A running record of test runs for the MajiShamba Extension Agent. All runs use
`.venv/bin/python -m pytest -q` with `config.settings.development`
(`LLM_PROVIDER=none`, `MAJISHAMBA_SYNC_RUN=1`).

## Baseline — `origin/main` @ `26309cf` (before Phase 1)

```
3 failed, 799 passed, 1 skipped, 2 warnings in 101.04s
```

- **Skipped (1):** `tests/e2e/test_browser.py` — Playwright; requires
  `RUN_PLAYWRIGHT_TESTS=1` and `playwright install chromium`. Not run in CI.
- **Failed (3), pre-existing and unrelated to this work:**
  - `tests/integration/test_llm_provider.py::test_provider_status_report`
  - `tests/integration/test_llm_provider.py::test_paid_model_not_selected_automatically`
  - `tests/integration/test_llm_provider.py::TestProviderAndGraphDeterministic::test_provider_failure_uses_accurate_fallback_status`

  These three depend on a configured LLM provider and fail in an environment
  with `LLM_PROVIDER=none`. They are not affected by the Phase 1 changes
  (different app, no shared code path) and were failing before this branch.

## Phase 1 — `feature/base44-api` (after Phase 1 work)

```
3 failed, 825 passed, 1 skipped, 2 warnings in 102.29s
```

- **799 → 825 passed:** +26 new tests in `tests/integration/test_api.py`, all
  passing.
- **3 failed:** identical to baseline (same three `test_llm_provider.py`
  cases). No new failures, no regressions.
- **1 skipped:** unchanged (Playwright).

### New test file: `tests/integration/test_api.py` (26 tests)

Run in isolation: `.venv/bin/python -m pytest tests/integration/test_api.py -q`
→ `26 passed in 4.77s`.

Coverage: token auth (missing/invalid/revoked/expired/insufficient-scope,
`X-API-Key` fallback, raw-token-never-stored), the per-request eligibility
re-check (demoted officer, suspended officer), `last_used_at` update, advisory
request endpoint (create/dedup/not-found/missing-field), approval endpoint
(approve/reject/version-mismatch/not-draft/not-found/invalid-decision), token
introspect/revoke, the `generate_api_token` command (success + non-officer
rejection), and two web-view regression tests confirming the service
extraction preserved web behaviour.

### Other checks

- `python manage.py makemigrations api` → created `apps/api/migrations/0001_initial.py`.
- `python manage.py check` → `System check identified no issues (0 silenced).`

## Phase 2 — Advisory integration (`feature/base44-api`)

```
837 passed, 1 skipped, 2 warnings in 103.14s
```

- **828 → 837 passed:** +9 new tests in `tests/integration/test_api.py`
  covering the two new read endpoints, the canonical request path, audit
  attribution, the run-status access rule, and the pipeline-failure path.
- **0 failed; 1 skipped** (Playwright, unchanged).
- **No migration:** the new `advisories:read` scope is a `Scope` enum value
  stored in the existing `scopes` JSONField — no schema change
  (`makemigrations --check` reports "No changes detected").

### New endpoints (roadmap §11, Phase 2)

- `POST /api/v1/advisories/` — endpoint 3 canonical path (alias
  `/advisories/request/` retained). Each request is audited as
  `advisory:request` with the token user as actor.
- `GET /api/v1/runs/<uuid>/` — endpoint 4, run-status polling. Returns
  `status` (`completed` / `completed_with_fallback` / `failed` …) and
  `result_advisory_id`; access = owner / officer / system admin.
- `GET /api/v1/advisories/<pk>/` — endpoint 5, advisory detail + serialized
  evidence + `content_version`; soft-deleted advisories return 404.

### Service / worker hardening (roadmap Phase 2 required work)

- `request_advisory_run` is now `@transaction.atomic` and locks the
  `FarmerCluster` row with `select_for_update`, closing the dedup TOCTOU.
- `execute_advisory_run` catches pipeline exceptions and records a `FAILED`
  run with `error_message` instead of propagating.

### New scope

`advisories:read` (eligibility: `is_officer() or is_system_admin()`).

## Phase 1 completion — endpoints 1 & 2 (`feature/base44-api`)

```
848 passed, 1 skipped, 2 warnings in 107.12s
```

- **837 → 848 passed:** +11 new tests in `tests/integration/test_api.py`
  (3 for the health endpoint, 8 for the clusters list).
- **0 failed; 1 skipped** (Playwright, unchanged); 2 pre-existing
  `RemovedInDjango60Warning`s in `apps/integrations/forms.py`.
- **No migration:** endpoints 1 & 2 add no model fields — health reuses the
  existing `HealthCheckView` and clusters reads `FarmerCluster` rows
  (`makemigrations --check` → "No changes detected"; `manage.py check` →
  0 issues).

### New endpoints (roadmap §A1 Table 2, endpoints 1 & 2)

- `GET /api/v1/health/` — endpoint 1, no auth. Reuses `HealthCheckView`
  (also served at `/health/health/`); returns status / database /
  migrations_pending / provider config; GET-only (405 otherwise); no secrets.
- `GET /api/v1/clusters/` — endpoint 2, "token (any active)". Page-based
  pagination (default 25, ceiling 100) and a `?q` filter on cluster_id /
  name / locality; returns the seven roadmap §A4 fields per cluster.

### New auth path

`any_active_token_required` (`apps/api/auth.py`) — the roadmap's "token (any
active)" path for read-list / reference-data endpoints: a valid, non-expired,
non-revoked token bound to an active user, with no scope check and no role
gate (a viewer-scoped or empty-scope token may read clusters).

### Response-shape note

The roadmap (§A1) specifies a `{"ok": true, "data": ...}` envelope; the
implementation uses flat payloads + `{"error": {...}}` uniformly across all
endpoints. Documented in `docs/implementation/03_endpoints.md`.

## How to reproduce

```bash
cd majishamba_fresh
.venv/bin/python -m pytest -q                       # full suite
.venv/bin/python -m pytest tests/integration/test_api.py -q   # Phase 1 + Phase 2
```
