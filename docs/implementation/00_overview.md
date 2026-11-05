# Phase 1 — Base44 public API: overview

## Goal

Expose a scoped, token-authenticated REST API at `/api/v1/` so an external
application (for example one built on the Base44 app builder) can drive the
two load-bearing operational actions — **requesting a draft advisory run** and
**recording an officer's approval decision** — without holding a Django
session. The API reuses the exact domain logic the server-rendered web views
use, so behaviour cannot drift between channels.

## In scope

- `apps/api` Django app with an `ApiToken` model (SHA-256-hashed, scoped,
  expiring, revocable, bound to an officer account).
- A `token_required` view decorator that authenticates a `Bearer` token and
  **re-checks the bound officer's eligibility on every request**.
- Four endpoints: `POST /api/v1/advisories/request/`,
  `POST /api/v1/approvals/`, `GET /api/v1/token/introspect/`,
  `POST /api/v1/token/revoke/`.
- A `generate_api_token` management command.
- Two extracted domain services: `request_advisory_run` (advisories) and
  `record_approval` (approvals), with the existing web views refactored to
  call them.

## Deliberately out of scope

- A run-status polling endpoint (the API returns a `run_id`; the existing web
  `/advisories/runs/<uuid>/` page remains the status view). Add when a
  consumer needs it.
- Rate limiting / quotas per token. Add before production hardening.
- OAuth / session-coupled auth. PAT-style bearer tokens are sufficient for a
  single trusted integration.
- A read/list API for advisories, clusters, or approvals. Only the two
  write-side operational actions are exposed for now.

## Branching

Work is on `feature/base44-api`, branched from `origin/main` (`26309cf`,
"Add offline field findings sync"). No `main` history is rewritten; the
branch is additive (new app, new migration, two service modules, two view
refactors, settings/urls wiring).

## Files added / changed

See `docs/implementation/TRACEABILITY.md` for the requirement-to-artifact map.
