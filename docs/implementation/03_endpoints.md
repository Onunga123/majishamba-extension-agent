# API endpoints — `apps/api/views.py`, `apps/api/urls.py`

Mounted at `path("api/v1/", include(("apps.api.urls", "api"), namespace="api"))`
in `config/urls.py`. All endpoints are JSON in/out. All except `GET /health/`
require a Bearer token.

> **Response shape.** The roadmap (§A1) describes a uniform
> `{"ok": true, "data": ...}` / `{"ok": false, "error": {...}}` envelope. The
> implementation deliberately uses **flat** success payloads (the resource
> object directly) and a bare `{"error": {"code", "message", ...}}` on failure,
> applied uniformly across every endpoint. This keeps each response a single
> typed object and avoids a wrapper a Base44 client must unwrap at every call
> site; the deviation is consistent across the whole `/api/v1/` surface.

## `GET /api/v1/health/` — no auth (endpoint 1)

Unauthenticated health/readiness check for load balancers and monitoring.
Reuses the existing `HealthCheckView` (`apps/dashboard/health.py`), also served
at `/health/health/`, so the API and operational health checks share one
implementation.

**Response** (200, no auth)
```json
{
  "status": "ok",
  "database": "ok",
  "migrations_pending": false,
  "llm_provider": "openrouter",
  "weather_provider": "open_meteo",
  "version": "0.1.0"
}
```
`status` is `"ok"` or `"degraded"` (degraded if the database is unreachable or
migrations are pending). No secrets or tokens are exposed. GET-only; other
methods return 405.

## `GET /api/v1/clusters/` — token (any active) (endpoint 2)

List farmer clusters — the reference data Base44 retrieves to browse clusters
and submit advisory requests. Any valid, non-expired, non-revoked token bound
to an active user may call this; no specific scope or role is required (the
roadmap's "token (any active)" path, `any_active_token_required` in
`apps/api/auth.py`).

**Query parameters**
| param | default | notes |
| --- | --- | --- |
| `page` | 1 | 1-based page number |
| `page_size` | 25 | capped at 100 (roadmap §A1 ceiling) |
| `q` | — | case-insensitive substring on `cluster_id`, `name`, `locality` |

**Responses**
| status | meaning | body / code |
| --- | --- | --- |
| 200 | page of clusters | see below |
| 401 | no token | `missing_token` |
| 403 | revoked / expired / inactive user | `token_revoked` / `token_expired` / `user_inactive` |

```json
{
  "count": 14, "page": 1, "page_size": 25,
  "next": null, "previous": null,
  "results": [
    {"cluster_id": "KACH-01", "name": "Sori", "locality": "Sori",
     "ward": "Kachieng", "centroid_lat": -0.963, "centroid_lon": 34.445,
     "coordinates_verified": true}
  ]
}
```
Each result carries exactly the seven roadmap §A4 fields. `next`/`previous` are
absolute URLs for the adjacent page, or `null` at the boundary.

## `POST /api/v1/advisories/` — scope `advisories:request`

Request a draft advisory run for a cluster (endpoint 3). The alias
`POST /api/v1/advisories/request/` is kept for earlier clients and maps to the
same handler.

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

`status` is the `AdvisoryRun.Status` value at creation time (`queued`); poll
`GET /api/v1/runs/<run_id>/` (endpoint 4) until it reaches `completed` /
`completed_with_fallback` or `failed`. Each request is logged as an
`advisory:request` audit event with the token user as the actor.

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

## `GET /api/v1/runs/<run_id>/` — scope `advisories:read`

Return the status of an advisory run (endpoint 4). A caller polls this after
`POST /advisories/` until `status` settles.

**Responses**
| status | meaning | body / code |
| --- | --- | --- |
| 200 | run found | see below |
| 401/403 | auth (as above); a viewer token is `not_eligible` | |
| 404 | unknown run | `run_not_found` |

```json
{
  "run_id": "...", "status": "completed_with_fallback",
  "cluster_id": "KACH-01", "current_message": "Draft ready for officer review",
  "created_at": "...", "started_at": "...", "finished_at": "...",
  "result_advisory_id": 42, "error_message": "", "generation_mode": "fallback_template"
}
```
`status` ∈ `{queued, running, waiting_for_model, validating, completed,
completed_with_fallback, failed}`. When `status` is `completed[_with_fallback]`,
fetch the draft via endpoint 5 using `result_advisory_id`; when `failed`,
`error_message` carries the reason. Access mirrors the web
`AdvisoryRunStatusView`: the run owner, any officer, or a system admin.

## `GET /api/v1/advisories/<advisory_pk>/` — scope `advisories:read`

Return an advisory draft and its evidence (endpoint 5).

**Responses**
| status | meaning | body / code |
| --- | --- | --- |
| 200 | advisory found | see below |
| 401/403 | auth (as above) | |
| 404 | unknown or soft-deleted advisory | `advisory_not_found` |

```json
{
  "id": 42, "status": "draft", "cluster_id": "KACH-01",
  "recommendation_type": "plant", "summary": "...", "body": "...",
  "confidence": "medium", "limitations": "...", "content_version": 3,
  "evidence": [{"source_type", "source_ref", "claim", "is_stale",
                "retrieved_at", "source_observed_at", "source_url"}],
  "crop": "maize", "season": "short_rains",
  "county": "Migori", "sub_county": "Nyatike", "ward": "Kachieng",
  "model_name": "...", "generation_mode": "fallback_template",
  "created_at": "...", "updated_at": "..."
}
```
Soft-deleted advisories are hidden (404) — the default manager excludes them.
`content_version` is the optimistic-concurrency guard an approval must match.
