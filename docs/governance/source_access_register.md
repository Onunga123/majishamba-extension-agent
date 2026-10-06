# Source-access register — Kachieng AI Agent

This register documents the **actual** public access methods, API availability, publication frequency, geographic coverage, reuse terms, and implementation status for each authority the Kachieng AI Agent ingests from or references. It is built from direct inspection of the official websites (last verified 2026-10-05), not from search-result titles or URLs.

**Reading order:** Weather (KMD) → Agronomic guidance (KALRO) → Pest notices (KEPHIS / KALRO / Migori County) → Officer field reports → Borrowed MCP filesystem server.

The Kachieng AI Agent **never** relabels synthetic content as real. The default state for each real-data source is "no current verified notice" — the dashboard and tools say exactly that, not "no pest risk".

---

## 1. Kenya Meteorological Department (KMD)

| Field | Value |
|---|---|
| Authority | Kenya Meteorological Department |
| Official source page | https://meteo.go.ke/ |
| Product/documents | Daily Forecast, 5 Days Forecast, 7 Days Forecast, County Forecasts, Lake Victoria Fishing Forecast, Marine Forecasts (Daily, 7 Days). All listed on https://meteo.go.ke/our-products/ |
| Public access method | Web pages on meteo.go.ke. The 5/7-day forecasts are presented as web HTML and downloadable PDFs. County forecasts are county-specific pages. Lake Victoria forecasts cover the Lake Victoria Basin (regional, includes Migori). |
| API availability | **No public API found.** No JSON/XML endpoint documented on meteo.go.ke or in the FAQ. The `kmddl.meteo.go.ke` climate-data library is an interactive web GIS, not a programmatic forecast API. |
| Publication frequency | Daily (Daily Forecast); every 1–7 days (5/7 Days Forecast); daily for Lake Victoria Fishing Forecast. County Forecasts updated daily. Seasonal outlooks published monthly or per rain season. |
| Geographic coverage | National (Daily Forecast); Lake Victoria Basin (Fishing Forecast — includes Migori); per-county (County Forecasts); the meteo.go.ke FAQ does not list a per-ward or per-locality forecast. |
| Access/reuse terms | Public forecast bulletins may be cited with attribution to "Kenya Meteorological Department". No open-data licence is published on meteo.go.ke. Bulk redistribution, prefetching, or republishing is not granted. We cite the bulletin and link to the official page; we do not republish the full bulletin text. |
| Access limitations | No programmatic API → manual retrieval required. No per-ward or per-locality forecast (the smallest geographic unit published is county-level). Lake Victoria forecasts cover Migori as part of the Lake Victoria Basin, not as a Nyatike or Kachieng observation. |
| Last successful retrieval | 2026-10-05 (manual inspection of https://meteo.go.ke/our-products/). Forecast bulletins themselves were not committed to the repo; we record metadata only and link to the official page. |
| Implementation status | **Provider adapter implemented** at `apps/integrations/kmd.py` — metadata-only path. The adapter records: product_type, publication_date, valid_from, valid_to, geographic_scope, coverage_level, source_url, retrieved_at. Forecast content is NOT fetched or republished — the dashboard links to the official KMD page. The adapter does not invent rainfall totals or onset. Numeric `rainfall_mm` is left NULL when the bulletin does not specify a value (most KMD qualitative bulletins say "showers and thunderstorms", not "X mm"). |

### Geographic representation rule

A Lake Victoria Basin regional forecast that includes Migori is labelled in the dashboard as **"Regional forecast covering Migori"** — not as a Nyatike station observation and not as a Kachieng-local forecast. We do **not** interpolate locality-level rainfall or onset from regional prose.

### Quantitative data rule

Numeric rainfall is stored **only** when the bulletin explicitly provides:
- units (mm), period, geographic scope, observation/forecast distinction, range/uncertainty where supplied.

If the bulletin says "showers and thunderstorms", we store that description in `forecast_summary` and leave `rainfall_mm` NULL. **NULL means "not provided", not zero.** The dashboard shows **"Rainfall amount: Not specified in this bulletin"** — never "Rainfall: None mm".

### Rainfall onset rule

`onset_status` is stored as `"unknown"` unless:
- KMD explicitly reports onset for an applicable area, OR
- an authorized officer records a verified local observation (officer field report).

We do **not** infer confirmed onset from a 5/7-day forecast or from monthly outlook. Unsupported numerical onset thresholds (e.g. "3 consecutive rainy days ≥ 5 mm/day") are removed from real-data mode; the fallback template now treats onset as `unknown` when the source does not specify it.

---

## 2. KALRO — agronomic guidance

| Field | Value |
|---|---|
| Authority | Kenya Agricultural and Livestock Research Organization |
| Official source pages | https://www.kalro.org/ and https://keep.kalro.org (KALRO e-Knowledge for Extension Providers) |
| Product/document | KCEP-CRAL integrated soil fertility and water management extension manual (April 2021, ISBN documented on ResearchGate and on the KALRO KEEP site). Maize Extension Manual hosted at https://statistics.kilimo.go.ke/files/bookpage/KENYA_Maize-Extension-Manual.pdf. Other KALRO manuals and factsheets are also on https://keep.kalro.org. |
| Public access method | Web pages with PDF downloads. Some materials on `keep.kalro.org` are openly browsable. The 2021 KCEP-CRAL maize manual is on a Ministry of Agriculture statistics subdomain (`statistics.kilmo.go.ke`). |
| API availability | **No public API found.** `keep.kalro.org` is a CKAN-style repository; bulk download via CKAN API may exist but is not documented for the maize manual specifically. |
| Publication frequency | Manuals are published per project/season; no fixed schedule. Factsheets updated irregularly. |
| Geographic coverage | National; sub-national in some project reports (e.g. KCEP-CRAL targeted specific counties, not including Migori-specific local calendars). |
| **Access/reuse terms** | **© KALRO 2021. All rights reserved.** The KCEP-CRAL maize manual's copyright notice restricts reproduction, database storage, and transcription without prior written permission. Public availability is **not** an open-data licence. The project's MIT licence does **not** cover third-party documents. |
| Access limitations | **Permission-pending.** Detailed ingestion (full-text index, searchable corpus, reproduction in advisories) requires prior written permission from KALRO. We record bibliographic metadata + the official source URL only; we do **not** commit the PDF to the repo, do not extract passages into the agent's evidence, and do not populate a searchable corpus. |
| Last successful retrieval | 2026-10-05 (manual web inspection of `keep.kalro.org` and the `statistics.kilmo.go.ke` PDF link). PDF was not downloaded into the repo. |
| Implementation status | **Bibliographic metadata only.** The CropCalendar model now stores `source_authority="KALRO"`, `source_url` to the official PDF/page, `licence_or_permission_basis="© KALRO 2021 — all rights reserved; permission pending"`, `permission_status="permission_pending"`, `extraction_review_status="not_extracted"`. We **do not** display KALRO planting-date rules (Sep 15–Oct 20), onset thresholds (3 rainy days ≥ 5 mm/day), variety recommendations (H614, PH4, WH505), blanket fertilizer type/rate/timing, or pest-scouting stage from the manual — those rules are not ingested unless and until permission is granted. The dashboard says "Agronomic guidance: permission-pending for KALRO maize manual ingestion". The fallback template does not emit those specific dates or rules. |

### Important rule on KALRO content

**Do not call a national manual a "KALRO Migori short-rains calendar".** The KCEP-CRAL manual is a national-level reference; it is not a county-specific calendar and does not establish planting dates for Kachieng Ward. We label it as a "national agronomic reference manual" only.

**Do not commit the full PDF to the public repository.** Public availability is not an open-data licence. The project's MIT licence does not cover third-party documents.

---

## 3. KEPHIS — pest notices

| Field | Value |
|---|---|
| Authority | Kenya Plant Health Inspectorate Service |
| Official source page | https://www.kephis.org/ |
| Product/documents | Phytosanitary field inspection manuals, import/export regulations, occasional pest alerts. KEPHIS is referenced in IPPC and STDF documents as a sub-regional pest early-warning partner. |
| Public access method | Web pages; some PDFs. No public alert API or RSS feed documented. |
| API availability | **No public API found.** |
| Publication frequency | Pest notices are irregular; no fixed schedule. |
| Geographic coverage | National; some sub-regional (EAC) collaborations. |
| Access/reuse terms | Public notices may be cited with attribution. No open-data licence published. |
| Access limitations | No programmatic API; no real-time alert feed. Pest notices are published as ad-hoc announcements. A KEPHIS factsheet establishes background guidance, **not** a current outbreak in Kachieng. |
| Last successful retrieval | 2026-10-05 (manual web inspection). No current fall-armyworm outbreak notice for Migori County was found on the KEPHIS homepage. |
| Implementation status | **No active ingestion.** The PestAlert model's `source_authority` field accepts `"KEPHIS"` for officer-supplied reports; no automatic scraping is performed. Default state: "No current verified official pest notice available for this area." |

---

## 4. KALRO pest factsheets

| Field | Value |
|---|---|
| Authority | KALRO |
| Source page | https://www.kalro.org/ and https://keep.kalro.org |
| Product | Pest factsheets (fall armyworm, larger grain borer, etc.). |
| Public access method | Web pages with PDFs. |
| API availability | **No public API found.** |
| Publication frequency | Irregular; factsheets are reference documents, not current outbreak notices. |
| Geographic coverage | National reference. |
| Access/reuse terms | Same as KALRO manuals — © KALRO, all rights reserved; permission pending. |
| Access limitations | A KALRO pest factsheet establishes **background guidance** about a pest, not a current outbreak in Kachieng. We do not relabel a factsheet as a current alert. |
| Implementation status | **Reference only.** PestAlert can record `source_authority="KALRO"` and `product_type="reference_factsheet"` with `verification_status="background_reference"`. The dashboard shows these as background references, not as active notices. |

---

## 5. Migori County agricultural authorities

| Field | Value |
|---|---|
| Authority | Migori County Government — Department of Agriculture |
| Official source page | https://migori.go.ke/ (county government). No dedicated agriculture-department page with public pest bulletins was found. |
| Product/documents | County Annual Development Plan (CADP), occasional sector reports. No public pest-alert feed. |
| Public access method | PDF downloads on the county website. |
| API availability | **None.** |
| Publication frequency | Annual (CADP); ad-hoc sector reports. |
| Geographic coverage | Migori County. |
| Access/reuse terms | Public documents; cited with attribution. No open-data licence. |
| Access limitations | No real-time pest bulletin. The 2018 fall-armyworm news article (Standard Media, citing then-Governor Obado) is a press item, not an official notice. |
| Last successful retrieval | 2026-10-05 (manual web inspection). No current (2025–2026) fall-armyworm outbreak notice for Migori County was found. |
| Implementation status | **No active ingestion.** Officer-supplied county reports can be recorded via the PestAlert model with `source_authority="Migori County Department of Agriculture"` and `verification_status="officer_field_report"` — but this requires an authorized officer to upload the report; the system does not automatically fetch county reports. |

---

## 6. Officer-supplied field reports (PEST / WEATHER)

When no public feed exists, the system supports an authorized officer uploading an authentic county report or a verified local observation. This is **not** an official bulletin — it is an officer field report.

| Field | Value |
|---|---|
| Authority | The named extension officer who uploads the report. |
| Source | Officer field report (uploaded by a logged-in extension officer). |
| Verification basis | Officer records: author name, observation date, coverage (e.g. "Kachieng Ward"), verification status = `officer_field_report`. |
| Implementation status | The PestAlert and WeatherSignal models accept `source_authority="Officer field report"` and `verification_status="officer_field_report"`. A user-uploaded file is **not** automatically a KEPHIS/KALRO publication. The dashboard labels these clearly as officer field reports. |

---

## 7. Borrowed MCP filesystem server

| Field | Value |
|---|---|
| Authority | Official MCP filesystem server (`@modelcontextprotocol/server-filesystem`) |
| Source | npm package `@modelcontextprotocol/server-filesystem`. |
| Public access method | `npx -y @modelcontextprotocol/server-filesystem <allowed-dir>` over stdio. |
| API availability | Yes — speaks the official MCP protocol over stdio. Tools: `read_file`, `list_files`, etc. |
| Geographic coverage | n/a (filesystem). |
| Access/reuse terms | MIT-licensed MCP server. The contents of files in `docs/calendars/` are subject to the source's own licence — currently only the synthetic sample placeholder calendar is there, which is MIT. |
| Access limitations | Restricted to a single approved directory (`docs/calendars/`). The agent does not read arbitrary files. |
| Last successful retrieval | 2026-10-05. The borrowed MCP server is invoked from `apps/agents/graph.py:load_calendar_from_borrowed_mcp` and the call is logged to `AuditEvent(tool_name="borrowed_filesystem_mcp")`. |
| Implementation status | **Active in the agent graph.** The MCP filesystem server is invoked over stdio via the official MCP client (`mcp.client.stdio.stdio_client` + `ClientSession`) when `MAJISHAMBA_BORROWED_MCP_USE_NPX=1` and Node/npx are available. If npx is unavailable, the node falls back to a direct file read of the **approved** calendar placeholder (`docs/calendars/sample_calendar.txt`) — still logged as a `borrowed_filesystem_mcp` audit event so the call is visible to the officer. **No synthetic KALRO rules are loaded from this server** — only the approved placeholder, which is MIT-licensed and clearly labelled synthetic. KALRO content is **not** loaded here until permission is granted. |

---

## Summary of honest availability states

The dashboard and tools now show one of these states for each data class:

| State | Meaning | Display |
|---|---|---|
| `current_official` | A current, applicable official bulletin was ingested (e.g. KMD 7-day forecast for Migori) | Shows: product title, authority, coverage, issue date, validity, qualitative forecast, link |
| `regional_context` | A regional forecast that covers the area but is not locality-specific | Shows: "Regional forecast covering Migori" + coverage note |
| `permission_pending` | Source exists but ingestion is permission-pending (e.g. KALRO maize manual) | Shows: "Agronomic guidance: permission-pending for KALRO maize manual ingestion" |
| `officer_field_report` | An authorized officer uploaded a verified local observation | Shows: "Officer field report — <author>, <date>, <coverage>" |
| `synthetic_test_scenario` | Synthetic content kept only for tests / demo with the deterministic fallback | Shows: "Synthetic demonstration signal — not a live feed / not a live alert" |
| `no_current_notice` | No current applicable official notice found | Shows: "No current verified official pest notice available for this area." + "This does not establish that pests are absent. Local scouting and extension-officer verification remain necessary." |

**Never shown:**
- "No pest risk" (we never claim pests are absent)
- "Live station feed" (we never call a published bulletin a live station feed)
- "Rainfall: None mm" (NULL means not provided, not zero)

---

## Data conduct

- Synthetic household and plot records remain clearly labelled. This update does not authorize collection of real household data.
- We do not contact authorities or send requests automatically.
- We do not use proxies to evade blocking, do not prefetch, do not bulk-download from public community tile services, do not bypass authentication or payment requirements.
- We respect robots directives, service terms, and reasonable rate limits.
- We do not invent endpoints, authentication methods, RSS feeds, or data schemas.
