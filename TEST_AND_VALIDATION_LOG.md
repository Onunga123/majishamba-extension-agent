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

## How to reproduce

```bash
cd majishamba_fresh
.venv/bin/python -m pytest -q                       # full suite
.venv/bin/python -m pytest tests/integration/test_api.py -q   # Phase 1 only
```
