# Phase 3 — Base44 integration

## Goal

Connect a Base44-built app (the "Superagent") to Kachieng' over `/api/v1/` and
validate the end-to-end advisory-generation flow: browse clusters, request an
advisory, poll to completion, and display the draft with its evidence. This is
the roadmap's Phase 3 (roadmap §11, Phase 3).

The API endpoints Phase 3 needs (1, 2, 3, 4, 5) are all built and on
`feature/base44-api`. **The remaining Phase 3 work is Base44-side and Render
configuration** — the roadmap is explicit: *"Files affected: Base44 project
(outside this repo); Render dashboard (environment variables, no code); no
Kachieng' repository changes beyond environment."* This document is the
authoritative hand-off so that Base44-side work is a straightforward adaptation
task (roadmap estimate: 6–8 hours).

## Why this doc exists: the real contract ≠ roadmap §A4

Roadmap §A4 sketches an *idealized* API: a `{"ok": true, "data": ...}` envelope,
a `kng_` token prefix, `202` on advisory request with `advisory_id` in the
response, a `409 duplicate_run` on re-submission, and a `/advisories/<pk>/approve/`
path. **The implementation on `feature/base44-api` differs in several concrete
ways.** A Base44 developer building against §A4 as-written will break against
the live API. This document describes what the API actually does, and the
reference Deno client under `base44_reference/` matches it.

### Deviation table — roadmap §A4 vs. actual implementation

| # | Roadmap §A4 (idealized) | Actual implementation (`feature/base44-api`) | What Base44 does about it |
| --- | --- | --- | --- |
| 1 | token prefix `kng_<32>` | `majishamba_<…>` (whatever `generate_api_token` prints) | Store the printed raw token verbatim; prefix is cosmetic |
| 2 | envelope `{"ok":true,"data":…}` / `{"ok":false,"error":…}` | **flat** payload on success (the resource object directly); `{"error":{"code","message",…}}` on failure | Read the resource at the top level, not under `.data`; read errors at top-level `error` |
| 3 | `POST /advisories/` → `202 {run_id, status, advisory_id, generation_mode, current_message}` | `201` (new run) or `200` (dedup reuse) → `{run_id, status, created}` (no `advisory_id` in the POST response) | Poll `GET /runs/<run_id>/` to get `status` + `result_advisory_id`; do not expect `advisory_id` from the POST |
| 4 | duplicate within 30 min → `409 duplicate_run` with `run_id` | `200 {created: false, run_id: <existing>}` | Treat `created === false` as a reused run; use the returned `run_id` to poll |
| 5 | endpoint 7 `POST /advisories/<pk>/approve/` | `POST /approvals/` with `advisory_id` in the JSON body | Phase 4 (approval workflow). Base44 approval calls `/approvals/`, not `/advisories/<pk>/approve/` |
| 6 | endpoint 6 `GET /advisories/?cluster=<id>` (list advisories by cluster) | **not built** | Phase 4+. Base44 browses via `/clusters/` (endpoint 2) and reads each advisory via `/advisories/<pk>/` (endpoint 5) |
| 7 | endpoint 8 `GET /tasks/` (follow-up tasks) | **not built** | Phase 4+ |
| 8 | endpoint 9 `GET /audit/` (restricted audit trail) | **not built** | Phase 4+ |

Two operational endpoints exist that §A4's table does not number but Base44 may
use: `GET /api/v1/token/introspect/` (verify a token's scopes and bound user)
and `POST /api/v1/token/revoke/` (self-revoke a token).

> **Decision (recorded): align vs. document.** Aligning the API to §A4 would
> mean switching to the envelope, changing the token prefix, returning `409` on
> dedup, renaming `/approvals/` to `/advisories/<pk>/approve/`, and building
> endpoints 6/8/9 — all of which break the 848 passing tests and the already-
> shipped Phase 1/2 contract. We chose **document the real contract and ship a
> matching reference client**, the lower-risk path for the pre-festival
> critical path. Strict §A4 alignment can be revisited post-event.

## The Superagent flow (Phase 3 acceptance path)

This is the exact sequence Base44 drives. All responses are the real shapes.

### 0. Authenticate (every request)

Every request except `/health/` carries `Authorization: Bearer <raw-token>`.
The token is a `majishamba_…` string printed once by `generate_api_token`; it
is looked up by its SHA-256 hash, so only the raw value the client holds works.
The bound user's eligibility is re-checked on every request (a suspended or
demoted officer's token stops working immediately).

### 1. `GET /api/v1/health/` (no auth)

```http
GET /api/v1/health/
```
```json
{"status":"ok","database":"ok","migrations_pending":false,
 "llm_provider":"openrouter","weather_provider":"open_meteo","version":"0.1.0"}
```
Use this to pre-warm the service before a demo (Render free-tier cold start is
~30–40 s). `status` is `"degraded"` if the DB is down or migrations are pending.

### 2. `GET /api/v1/clusters/` (any active token)

```http
GET /api/v1/clusters/?page_size=50
Authorization: Bearer majishamba_…
```
```json
{"count":14,"page":1,"page_size":50,"next":null,"previous":null,
 "results":[{"cluster_id":"KACH-01","name":"Sori","locality":"Sori",
            "ward":"Kachieng","centroid_lat":-0.963,"centroid_lon":34.445,
            "coordinates_verified":true}]}
```
Page-based pagination (default 25, ceiling 100). `?q=` filters on `cluster_id`,
`name`, `locality`. `next`/`previous` are absolute URLs or `null`.

### 3. `POST /api/v1/advisories/` (officer token)

```http
POST /api/v1/advisories/
Authorization: Bearer majishamba_…   # an OFFICER token
Content-Type: application/json

{"cluster_id":"KACH-01"}
```
```json
{"run_id":"a1b2c3d4-…","status":"queued","created":true}   # 201 Created
```
`created: false` (HTTP `200`) means a recent in-flight run for this cluster was
reused (30-min dedup) — use the returned `run_id` to poll. A viewer token is
rejected with `403 not_eligible`; an unknown cluster is `404 cluster_not_found`.

### 4. `GET /api/v1/runs/<run_id>/` (owner / any officer / system admin) — poll

```http
GET /api/v1/runs/a1b2c3d4-…/
Authorization: Bearer majishamba_…
```
```json
{"run_id":"a1b2c3d4-…","status":"completed_with_fallback",
 "cluster_id":"KACH-01","current_message":"Draft ready for officer review",
 "created_at":"…","started_at":"…","finished_at":"…",
 "result_advisory_id":17,"error_message":"","generation_mode":"fallback_template"}
```
Poll every **2–3 seconds** while `status` is non-terminal
(`queued` / `running` / `waiting_for_model` / `validating`). Stop at
`completed` / `completed_with_fallback` (then fetch the advisory via
`result_advisory_id`) or `failed` (surface `error_message`). In demo config
(`MAJISHAMBA_SYNC_RUN=1`) the run completes synchronously within the POST
request, so the first poll already returns a terminal status.

### 5. `GET /api/v1/advisories/<advisory_pk>/` (any active token) — display

```http
GET /api/v1/advisories/17/
Authorization: Bearer majishamba_…
```
```json
{"id":17,"status":"draft","cluster_id":"KACH-01",
 "recommendation_type":"plant","summary":"…","body":"…",
 "confidence":"medium","limitations":"…","content_version":3,
 "evidence":[{"source_type":"weather","source_ref":"WeatherSignal#1",
              "claim":"Onset likely within the planting window.","is_stale":false,
              "retrieved_at":"…","source_observed_at":null,"source_url":null}],
 "crop":"maize","season":"short_rains","county":"Migori","sub_county":"Nyatike",
 "ward":"Kachieng","model_name":"…","generation_mode":"fallback_template",
 "created_at":"…","updated_at":"…"}
```
Soft-deleted advisories return `404 advisory_not_found`. `content_version` is
the optimistic-concurrency guard an approval (Phase 4) must match.

## Token provisioning

Phase 3 needs a **demo officer token** (to request advisories and read) and a
**demo supervisor token** (the "second human" — Phase 3 acceptance: *"a second
human (supervisor) is configurable"*). Create them with the existing management
command, in the environment that owns the database you will demo against:

```bash
# Officer — can request advisories and read runs/advisories.
python manage.py generate_api_token \
  --user <officer-username> \
  --name "base44-demo-officer" \
  --scopes advisories:request advisories:read token:introspect \
  --days 90

# Supervisor — a second officer who can also approve (Phase 4) and read.
python manage.py generate_api_token \
  --user <supervisor-username> \
  --name "base44-demo-supervisor" \
  --scopes advisories:request advisories:read approvals:record token:introspect \
  --days 90
```

The command prints each raw token **once** (`Store this raw token …`). Paste it
into the Base44 encrypted secrets vault as `KACHIENG_API_TOKEN` (officer) and
`KACHIENG_API_TOKEN_SUPERVISOR` (supervisor). Only the SHA-256 hash is stored in
the database; the raw token is never retrievable. Two helper scripts
(`scripts/provision_base44_tokens.{ps1,sh}`) wrap both commands.

## Render environment

Phase 3 requires these Render settings (no code change):

| env var | value | why |
| --- | --- | --- |
| `MAJISHAMBA_SYNC_RUN` | `1` | run the advisory pipeline synchronously within the request, so a single POST → poll completes (demo config) |
| `gunicorn --timeout` | `180` | pipeline completion can exceed the default 30 s timeout |
| `USE_POSTGRES` | `1` | durable storage across Render redeployments (already confirmed) |
| `LLM_PROVIDER` | `openrouter` (or `none` for a fallback-only dry run) | drives advisory generation; `none` forces `completed_with_fallback` |

Pre-warm the service (`curl /api/v1/health/`) before the demo to dodge the
Render free-tier cold start. Risks to rehearse (roadmap Phase 3): cold start /
sleep, OpenRouter rate limits under rehearsal, and token mis-scoping (a viewer
token silently cannot request advisories).

## What Base44 must build (checklist)

- [ ] Backend functions (Deno) calling `/api/v1/` — start from
      `docs/implementation/base44_reference/apiClient.ts`.
- [ ] Store the officer + supervisor tokens in Base44 encrypted secrets.
- [ ] Superagent workflow: browse clusters (2) → request (3) → poll (4) →
      display draft + evidence (5). See `base44_reference/superagent.ts`.
- [ ] Optional supervisor hand-off: a second human reads the same run + advisory
      using the supervisor token (Phase 3 acceptance).
- [ ] Render env set (`MAJISHAMBA_SYNC_RUN=1`, `gunicorn --timeout 180`).
- [ ] Pre-warm + smoke test: `curl /api/v1/health/` → 200;
      `curl -H "Authorization: Bearer …" /api/v1/clusters/` → 200.

## API-side acceptance (validated in this repo)

Phase 3's acceptance — *"Base44 retrieves clusters, submits an advisory, polls
to completion, and displays the draft with evidence; a second human (supervisor)
is configurable"* — is validated against the API by
`tests/integration/test_phase3_superagent_flow.py` (2 tests):

- `test_phase3_superagent_flow_health_clusters_request_poll_display` — the full
  flow end to end (health → clusters → request → poll → detail + evidence).
- `test_phase3_flow_second_human_supervisor_configurable` — a supervisor token
  reads the run + advisory the officer produced.

These prove the API supports the Phase 3 flow; the Base44 app that drives it is
built outside this repo.

## Reference client

`docs/implementation/base44_reference/` holds a copy-paste-ready Deno client:

- `types.ts` — TypeScript interfaces matching the real response shapes.
- `apiClient.ts` — `KachiengApiClient` with `health`, `listClusters`,
  `requestAdvisory`, `getRunStatus`, `getAdvisory`, and a `pollUntilCompleted`
  helper that polls every 2.5 s and fetches the advisory on completion.
- `superagent.ts` — `runSuperagentFlow(client, clusterId)` tying the steps
  together.
- `README.md` — how to drop it into Base44.

## Out of scope (deferred)

- Endpoints 6 (advisories list by cluster), 8 (tasks), 9 (audit) — Phase 4+.
- The approval path rename (`/approvals/` → `/advisories/<pk>/approve/`) and the
  §A4 envelope — see the align-vs-document decision above; revisited post-event.
- Rate limiting / per-token quotas — roadmap Phase 6.
- An OpenAPI spec + Swagger UI at `/api/v1/docs/` (roadmap §A1) — not required
  for the festival; the reference client + this doc substitute for it.
