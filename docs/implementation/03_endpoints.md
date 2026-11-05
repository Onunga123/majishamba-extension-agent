# API endpoints — `apps/api/views.py`, `apps/api/urls.py`

Mounted at `path("api/v1/", include(("apps.api.urls", "api"), namespace="api"))`
in `config/urls.py`. All endpoints are JSON in/out and require a Bearer token.

## `POST /api/v1/advisories/request/` — scope `advisories:request`

Request a draft advisory run for a cluster.

**Request body**
```json
{"cluster_id": "KACH-01"}
```

**Responses**
| status | meaning | body |
| --- | --- | --- |
| 201 | new run created | `{"run_id", "status": "queued", "created": true}` |
| 200 | recent in-flight run reused (30-min dedup) | `{"run_id", "status", "created": false}` |
| 400 | missing `cluster_id` | `{"error": {"code": "missing_field", ...}}` |
| 401 | no/invalid token | `missing_token` / `invalid_token` |
| 403 | revoked/expired/ineligible/no-scope | see `02_auth_and_eligibility.md` |
| 404 | unknown `cluster_id` | `cluster_not_found` |

`status` is the `AdvisoryRun.Status` value at creation time. The caller polls
the existing web status page at `/advisories/runs/<run_id>/` (a dedicated API
polling endpoint is intentionally deferred — see `00_overview.md`).

## `POST /api/v1/approvals/` — scope `approvals:record`

Record an officer's approval decision on a DRAFT advisory.

**Request body**
```json
{
  "advisory_id": 42,
  "decision": "approved",
  "content_version": 3,
  "comments": "Looks good",
  "create_followup": false,
  "task_type": "field_visit",
  "deadline": "2026-12-01"
}
```
`decision` ∈ `{approved, rejected, deferred, needs_evidence}`. `content_version`
must equal the advisory's current version (the version the caller reviewed).

**Responses**
| status | meaning | body / code |
| --- | --- | --- |
| 201 | recorded | `{"advisory_id", "status", "approval_id", "followup_task_id"}` |
| 400 | missing/invalid fields | `missing_field` / `invalid_decision` / `invalid_field` |
| 401/403 | auth (as above) | |
| 404 | unknown advisory | `advisory_not_found` |
| 409 | not DRAFT | `not_draft` |
| 409 | version changed | `version_mismatch` |

`status` is the advisory's new status (`approved`/`rejected`/`deferred`/`needs_evidence`).

## `GET /api/v1/token/introspect/` — scope `token:introspect`

Returns the metadata of the token making the request.
```json
{
  "active": true, "name": "...", "scopes": [...],
  "expires_at": "...", "last_used_at": "...", "created_at": "...",
  "user": {"id", "username", "role", "is_officer", "can_approve"}
}
```

## `POST /api/v1/token/revoke/` — scope `token:revoke`

Revokes the token making the request. Body ignored.
```json
{"revoked": true, "name": "..."}
```
Logged as `api_token:revoke` via `log_audit_event`.
