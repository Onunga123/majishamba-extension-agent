# Readiness Register — Kachieng AI Agent

Generated: 2026-10-07
Repository: https://github.com/Onunga123/majishamba-extension-agent

## Component Status

| Component | Current State | Evidence | Production Gap | Status |
|---|---|---|---|---|
| Django settings (production) | Hardened: SSL, HSTS, secure cookies, SECRET_KEY required | `config/settings/production.py` | None | ✅ IMPLEMENTED |
| Demo mode | OFF in production, ON in development | `production.py:31` | None | ✅ IMPLEMENTED |
| Synthetic data gating | `synthetic_flag` on all evidence models; excluded from dashboard + MCP | `apps/weather/models.py`, `apps/dashboard/views.py` | None | ✅ IMPLEMENTED |
| Soft-delete | `deleted_at`, `deleted_by`, `deletion_reason`; restore by supervisors | `apps/advisories/models.py` | None | ✅ IMPLEMENTED |
| Content validators | Reject "eee", unsupported onset, placeholder text | `apps/governance/validators.py` | None | ✅ IMPLEMENTED |
| LLM provider (OpenRouter) | Provider-neutral interface; OpenRouter default, Ollama optional | `apps/agents/llm_provider.py` | Free models produce "thinking" text; LLM calls succeed but JSON parse fails → fallback template used | ⚠️ IMPLEMENTED, LIVE CHECK PENDING |
| LLM provider (Ollama) | Preserved as optional provider | `apps/agents/llm_provider.py` | None | ✅ IMPLEMENTED |
| Weather automation | Open-Meteo API adapter; 7-day forecast; idempotent | `apps/integrations/open_meteo.py` | None | ✅ IMPLEMENTED, VERIFIED (live test passed) |
| Weather refresh command | `python manage.py refresh_weather` | `apps/integrations/management/commands/refresh_weather.py` | Cron/scheduler not set up (owner deploys) | ✅ IMPLEMENTED |
| Locality coordinates | Nominatim geocoding; 4/14 approved | `apps/geography/models.py` | 10 localities not found in OSM (honest "not yet recorded") | ✅ IMPLEMENTED |
| Map | Stadia Maps Alidade Smooth (free localhost) | `config/settings/base.py` | Needs API key for production domain | 🔑 OWNER KEY REQUIRED |
| MCP tools | 8 tools (6 read + 2 action); borrowed filesystem MCP | `apps/mcp_tools/tools.py` | None | ✅ IMPLEMENTED |
| LangGraph agent | 11 nodes + borrowed MCP + validation + fallback | `apps/agents/graph.py` | None | ✅ IMPLEMENTED |
| Advisory workflow | Request → evidence → draft → officer review → approval → task → audit | `apps/advisories/`, `apps/approvals/` | None | ✅ IMPLEMENTED |
| Audit trail | CSV export + structured JSON logging + actor attribution | `apps/audit/` | None | ✅ IMPLEMENTED |
| Nav badges | DRAFT advisory count + pending task count | `apps/dashboard/context_processors.py` | None | ✅ IMPLEMENTED |
| Officer upload forms | KMD bulletin + pest field report + published notice | `apps/integrations/views.py` | None | ✅ IMPLEMENTED |
| KALRO guidance | Bibliographic metadata only; permission-pending | `apps/integrations/kalro.py` | KALRO © all rights reserved | 📋 PERMISSION REQUIRED |
| Pest notices | Manual officer upload; no public API exists | `apps/integrations/pests.py` | No public pest-alert API found | ✅ MANUAL (by design) |
| Market data | Synthetic fixtures only | `data/fixtures/migori_market_prices.json` | No authorized live source identified | ⚠️ REAL DATA REQUIRED |
| Officer provisioning | `python manage.py create_officer` command | `apps/accounts/management/commands/create_officer.py` | Owner must create accounts | ✅ IMPLEMENTED |
| Health endpoint | `/health/health/` returns JSON status | `apps/dashboard/health.py` | None | ✅ IMPLEMENTED |
| Production deploy script | No fixtures; starts empty; documents onboarding | `scripts/deploy_production.sh` | None | ✅ IMPLEMENTED |
| Dockerfile + docker-compose | Production-ready with PostGIS, Valkey, Ollama | `Dockerfile`, `docker-compose.prod.yml` | None | ✅ IMPLEMENTED |
| Tests | 119 tests (118 pass, 1 skip) | `tests/integration/`, `tests/security/` | Playwright browser test skipped | ✅ VERIFIED |

## API Keys Required

| Service | Purpose | Key Location | Status |
|---|---|---|---|
| OpenRouter | LLM provider (advisory drafting) | https://openrouter.ai/keys → set `OPENROUTER_API_KEY` in `.env` | 🔑 Owner has account; key created |
| Stadia Maps | Production basemap | https://stadiamaps.com/ → set `KACHIENG_MAP_API_KEY` in `.env` | 🔑 OWNER KEY REQUIRED |
| Open-Meteo | Weather API | None required (free, no key) | ✅ No key needed |

## Processes Still Manual

1. **Pest notices:** No public API exists for KEPHIS/KALRO/Migori County. Officer uploads manually.
2. **KALRO guidance:** © KALRO 2021, all rights reserved. Permission-pending for content extraction.
3. **Advisory approval:** Always human. The agent recommends; the officer decides.
4. **Field-visit verification:** Always human. Automation prepares reminders.
5. **Officer account creation:** `create_officer` command + `changepassword`.
6. **Locality geocoding:** Nominatim lookup + manual approval of candidates.

## Operating Limits

| Resource | Limit | Cost |
|---|---|---|
| OpenRouter free models | Varies by model (429 rate limits common) | $0 (free tier) |
| Open-Meteo API | 10,000 calls/day, 5,000/hour, 600/minute | $0 (CC-BY 4.0) |
| Stadia Maps (free localhost) | No limit for localhost dev | $0 |
| Stadia Maps (production) | Free tier available; paid plans for higher traffic | $0 to ~$25/month |

## Upgrade Path (no purchase required)

- LLM: Switch from `openrouter/free` to a pinned model like `qwen/qwen3.7-flash` ($0.00000003/token — effectively free for low volume)
- Ollama: Install on a GPU machine for fully local, free inference
- Stadia Maps: Use free tier for production; upgrade only if traffic exceeds limits
