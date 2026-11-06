# Base44 reference client

A copy-paste-ready Deno/TypeScript client for the Kachieng' `/api/v1/` API, for
the Phase 3 Base44 Superagent integration. It matches the **actual** API on
`feature/base44-api`, not the idealized roadmap §A4 contract — see
`../09_phase3_base44_integration.md` for the deviation table.

## Files

- `types.ts` — TypeScript interfaces for every response shape + a typed `ApiError`.
- `apiClient.ts` — `KachiengApiClient` class. Methods: `health`, `listClusters`,
  `requestAdvisory`, `getRunStatus`, `getAdvisory`, `pollUntilCompleted`.
- `superagent.ts` — `runSuperagentFlow(client, options)` — the full Phase 3 flow
  (browse → request → poll → display).

No external dependencies — only the global `fetch`.

## Drop into Base44

1. Copy `types.ts`, `apiClient.ts`, `superagent.ts` into the Base44 backend
   functions directory.
2. Store the API token in Base44 encrypted secrets (e.g. `KACHIENG_API_TOKEN`).
   Create it with `python manage.py generate_api_token` on the deployed service
   (see `../09_phase3_base44_integration.md` → "Token provisioning").
3. In a Base44 backend function:

   ```typescript
   import { KachiengApiClient } from "./apiClient.ts";
   import { runSuperagentFlow } from "./superagent.ts";

   const client = new KachiengApiClient(
     Deno.env.get("KACHIENG_API_BASE_URL")!,       // https://kachieng-ai-agent.onrender.com
     Deno.env.get("KACHIENG_API_TOKEN")!,          // majishamba_… (officer)
   );

   // Pre-warm before a demo (Render free-tier cold start is ~30–40 s).
   await client.health();

   // Full Superagent flow: returns { cluster, run, advisory }.
   const result = await runSuperagentFlow(client, { clusterId: "KACH-01" });
   console.log(result.advisory.summary, result.advisory.evidence);
   ```

## Notes

- **Errors.** Any non-2xx response throws an `ApiError` with `.status`, `.code`,
  and `.message`. Catch it and surface the `.code` to the UI
  (`missing_token`, `invalid_token`, `token_expired`, `token_revoked`,
  `not_eligible`, `insufficient_scope`, `cluster_not_found`, `run_not_found`,
  `advisory_not_found`, …).
- **Polling.** `pollUntilCompleted` polls every 2.5 s (roadmap §A4: 2–3 s) and
  times out at 180 s (matches the `gunicorn --timeout 180` Render setting). In
  demo config (`MAJISHAMBA_SYNC_RUN=1`) the first poll already returns a
  terminal status.
- **Dedup.** `requestAdvisory` returns `{ created: false, run_id }` when a
  recent in-flight run for the cluster is reused (30-min window); `pollUntilCompleted`
  handles it transparently — just poll the returned `run_id`.
- **Modules.** Written for Deno (explicit `.ts` import extensions). If your
  Base44 bundler needs extensionless imports or a different module format,
  adjust the three `import` lines; the logic is unchanged.
