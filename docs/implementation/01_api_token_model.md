# ApiToken model — `apps/api/models.py`

## Storage

The raw token is never persisted. `ApiToken.create_token` generates
`<prefix> + secrets.token_urlsafe(32)` (default prefix `majishamba_`, from
`settings.MAJISHAMBA["API_TOKEN_NAME_PREFIX"]`), stores only
`sha256(raw)` in `token_hash` (unique, 64-char hex), and returns the raw token
to the caller exactly once. Lookup at request time re-hashes the presented
token and matches on `token_hash`. A DB leak therefore exposes no usable
credential.

## Fields

| field | purpose |
| --- | --- |
| `token_hash` | SHA-256 hex of the raw token; unique; not editable. |
| `name` | Human label (e.g. "Base44 production"). |
| `user` | FK to the officer whose authority the token carries. `on_delete=CASCADE` — deleting the officer invalidates the token. |
| `scopes` | `JSONField` list of `Scope` values granted. |
| `expires_at` | Optional expiry. Null = does not expire. |
| `revoked_at` | Set by `revoke()`. Null = active. |
| `last_used_at` | Updated via `touch()` (a raw `UPDATE`, no full save) on each authenticated request. |
| `created_at`, `created_by` | Audit. |

## Scopes

```
advisories:request  — POST /api/v1/advisories/request/
approvals:record    — POST /api/v1/approvals/
token:introspect    — GET  /api/v1/token/introspect/
token:revoke        — POST /api/v1/token/revoke/
```

Scopes are checked per request by the decorator (see `02_auth_and_eligibility.md`).
A token with only `token:introspect` cannot request advisories even if its
officer is eligible.

## Lifecycle helpers

- `is_active` — `revoked_at is None` and not past `expires_at`. Does **not**
  check the user's eligibility (that is scope-dependent, so it lives in the
  decorator).
- `has_scope(scope)` — membership test against `scopes`.
- `revoke()` — sets `revoked_at` if unset.
- `touch()` — `ApiToken.objects.filter(pk=...).update(last_used_at=now)`,
  avoiding model save signals on the hot auth path.

## Migration

`apps/api/migrations/0001_initial.py` creates the model with an index on
`(user, revoked_at)` to support "list this officer's active tokens" queries.
The migration is additive and safe to apply on a live DB.
