# Settings and security — `config/settings/base.py`, `config/urls.py`

## Settings changes

- **`INSTALLED_APPS`**: added `"apps.api"` (after `apps.integrations`).
- **`MAJISHAMBA` dict**: added the API token config block:
  - `API_TOKEN_NAME_PREFIX` (env `MAJISHAMBA_API_TOKEN_NAME_PREFIX`, default
    `majishamba_`) — the prefix prepended to every raw token so logs/scans can
    recognise a leaked token.
  - `API_TOKEN_EXPIRY_DAYS` (env `MAJISHAMBA_API_TOKEN_EXPIRY_DAYS`, default
    `90`) — the default expiry used by the management command.

## `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`

Both are already environment-driven (`env_list`). The API serves JSON to a
trusted external integration, not browser-rendered HTML, so the production
checklist is:

- Add the platform hostname(s) the Base44 app calls from to
  `MAJISHAMBA_ALLOWED_HOSTS`.
- `CSRF_TRUSTED_ORIGINS` does **not** need the API origin — API views are
  `csrf_exempt` and do not use the CSRF cookie. Leave it scoped to the
  server-rendered app's origins only.

## CSP

There is no Content-Security-Policy middleware in this project (no `django-csp`
dependency). The API returns `application/json` only — there is no
browser-rendered HTML to protect with a CSP, so none is needed for `/api/v1/`.
A CSP for the server-rendered pages is a separate, pre-existing concern and is
out of scope for this phase.

## Credential-in-URL cleanup (defensive)

The parent working clone's `origin` remote URL contained an embedded
credential (`https://Onunga123:<token>@github.com/...`) — the same leak pattern
that affected a previous token. It was rewritten to a clean
`https://github.com/...` URL so future fetches/pushes do not silently reuse a
plaintext credential from `.git/config`. Authentication for git should come via
a credential helper or a throwaway env-var-backed `http.extraheader`, never an
embedded URL.

## URL wiring

`config/urls.py` now includes:
```python
path("api/v1/", include(("apps.api.urls", "api"), namespace="api")),
```
The API is namespaced `api` so URL names are `api:request_advisory`,
`api:record_approval`, `api:token_introspect`, `api:token_revoke`.
