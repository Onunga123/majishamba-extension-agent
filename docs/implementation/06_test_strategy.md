# Test strategy — `tests/integration/test_api.py`

## Suite

26 tests covering the full API surface. Run with `.venv/bin/python -m pytest
tests/integration/test_api.py -q`.

## Coverage

**Token authentication (10):** missing token → 401; invalid token → 401;
`X-API-Key` header fallback accepted; revoked → 403; expired → 403;
insufficient scope → 403; raw token never stored (only its hash);
eligibility re-check blocks a demoted officer (`not_eligible`); eligibility
re-check blocks a suspended officer (`not_eligible`); `last_used_at` updated
on use.

**Advisory request endpoint (4):** creates a run (201, `created=true`,
`status=queued`); 30-min dedup reuses a run (200, `created=false`, same
`run_id`); unknown cluster → 404; missing field → 400.

**Approval endpoint (6):** approves a DRAFT (201, status advances,
`OfficerApproval` row created); rejects a DRAFT (201, `status=rejected`);
version mismatch → 409; not-DRAFT → 409; unknown advisory → 404; invalid
decision → 400.

**Token introspect/revoke (2):** introspect returns active metadata + user
eligibility flags; revoke sets `revoked_at` and blocks subsequent use.

**Management command (2):** `generate_api_token` creates a hashed token,
prints the raw token once, sets scopes and expiry; rejects a non-officer user
with `CommandError`.

**Web-view regression (2):** the refactored `RequestAdvisoryView` still
redirects to the run-status page; the refactored `ApprovalGateView` still
records an approval and advances status.

## Determinism notes

- `start_advisory_run_async` is monkeypatched to a no-op in the advisory
  tests so runs stay in `QUEUED` and the dedup window is observable. The real
  sync-run path is already exercised by the pre-existing advisory suite.
- Tests use an anonymous `Client` + `Authorization` header (no session), which
  is exactly how an external caller uses the API. `AccountStatusMiddleware`
  only acts on authenticated session users, so anonymous token-bearing requests
  pass through to the decorator unchanged.

## Baseline

Baseline before this phase: **799 passed, 3 pre-existing failures
(`tests/integration/test_llm_provider.py`, environment-dependent — they need a
real LLM provider and are unrelated to this work), 1 skipped (Playwright).**
This phase must not change that baseline other than adding the 26 new tests.
See `TEST_AND_VALIDATION_LOG.md` for the post-phase result.
