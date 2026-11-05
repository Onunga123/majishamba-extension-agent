# Rollout and rollback

## Deploy steps

1. Merge `feature/base44-api` into `main` (or deploy the branch).
2. Run `python manage.py migrate api` — applies `0001_initial` (creates the
   `api_apitoken` table). The migration is additive; no existing table is
   altered.
3. Set production env vars:
   - `MAJISHAMBA_ALLOWED_HOSTS` to include the hostname(s) the Base44 app
     calls from (plus the existing app hostname).
   - `MAJISHAMBA_API_TOKEN_EXPIRY_DAYS` if the default 90 is not appropriate.
4. Mint a token for the integration officer:
   ```bash
   python manage.py generate_api_token \
       --user <officer_username> \
       --name "Base44 production" \
       --scopes advisories:request approvals:record token:introspect token:revoke \
       --days 90
   ```
   The command prints the raw token **once**. Deliver it to the integration
   owner out of band (not in chat, not in git).
5. Confirm with the integration: `GET /api/v1/token/introspect/` with the
   Bearer token should return `{"active": true, ...}`.

## Production hardening (before broad rollout)

These are deliberately deferred (see `00_overview.md`) and should be addressed
before the API is exposed to more than one trusted integration:

- **Rate limiting / per-token quotas** — protect the advisory pipeline from a
  runaway caller. The 30-min dedup already prevents duplicate runs per
  officer+cluster, but not volume across clusters.
- **HTTPS only** — the API must be served over TLS; the token is a bearer
  credential.
- **Token rotation policy** — set a realistic `API_TOKEN_EXPIRY_DAYS` and
  rotate before expiry.
- **Audit review** — `api_token:revoke` and `officer_approval` audit events
  should be monitored; every API approval is logged with the same
  `officer_approval` action as web approvals.

## Rollback

The change is additive and reversible with no data loss:

1. Remove the `path("api/v1/", ...)` include from `config/urls.py` (or reverse
   the merge). The API stops being served immediately.
2. Optionally `python manage.py migrate api zero` to drop the
   `api_apitoken` table. This deletes token hashes (not credentials — only
   hashes are stored). Advisory and approval rows created via the API remain;
   they are ordinary `Advisory`/`OfficerApproval` rows indistinguishable from
   web-created ones.
3. The web views continue to work: the service extraction is internal and the
   refactored views call the same functions the old inline code did.

There is no schema migration of existing apps, so rolling back the API does
not require rolling back the advisories/approvals services — they are harmless
without the API mounted.
