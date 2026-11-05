# Authentication and the eligibility re-check — `apps/api/auth.py`

## How a request authenticates

`token_required(scope)` wraps a view. It is `csrf_exempt` — API clients cannot
use Django's session CSRF cookie, and the API does not depend on cookies at
all. The decorator:

1. Extracts the token from `Authorization: Bearer <token>` (an `X-API-Key`
   header is accepted as a fallback for clients that cannot set `Authorization`).
2. Hashes it and looks up `ApiToken` by `token_hash` (`select_related("user")`).
3. Rejects if the token is revoked (`token_revoked`, 403) or expired
   (`token_expired`, 403).
4. Loads the bound user; rejects if the user is not active (`user_inactive`, 403).
5. **Re-checks eligibility** for the requested scope (below).
6. Checks the token carries the requested scope (`insufficient_scope`, 403).
7. On success: sets `request.user` to the bound officer and `request.api_token`
   to the token, calls `token.touch()`, and invokes the view.

Missing/unrecognised tokens return 401 (`missing_token` / `invalid_token`);
all other failures return 403.

## The eligibility re-check (the load-bearing safety property)

Each scope maps to a live eligibility check on the bound user:

```
advisories:request → user.is_officer()
approvals:record    → user.can_approve()
token:introspect    → user.is_active
token:revoke        → user.is_active
```

`User.is_officer()` is `is_active and is_approved() and role in
{EXTENSION_OFFICER, SUPERVISOR}`. Because the check runs on every request, a
token whose officer is later **demoted to viewer**, **suspended**
(`approval_status=SUSPENDED`), or **deactivated** stops working immediately —
nobody has to remember to revoke the token. This mirrors the guarantees the
session-based `AccountStatusMiddleware` already gives the web app.

The check is independent of the token's own validity: a non-expired,
non-revoked token is still rejected if the officer it belongs to no longer
qualifies. This is tested by `test_eligibility_recheck_blocks_demoted_officer`
and `test_eligibility_recheck_blocks_suspended_officer`.

## Why `csrf_exempt` is safe here

These views accept only `application/json` (or no body), never read from
`request.POST`, and never trust the session cookie. There is no CSRF surface:
a browser-initiated cross-site `fetch` with a JSON body and a Bearer header is
blocked by the same-origin policy on the response unless CORS is configured
(it is not), and cannot fabricate a valid Bearer token without already having
it.

## Error envelope

Every failure returns `{"error": {"code": ..., "message": ..., ...}}` with a
stable `code` clients can branch on. See `03_endpoints.md` for the full table.
