# Synthetic data notice — MajiShamba Extension Agent

## Statement

**All household and plot records in this repository are SYNTHETIC.** No real Nyatike household names, plot coordinates, phone numbers, or yields are used. The fixtures in `data/fixtures/*.json` clearly mark this in `notes` fields and in household/plot representative names (`Synthetic rep — Kamau M.`, `Synthetic — Head A`, etc.).

Aggregate weather, pest and market signals in the fixtures are **synthetic summaries** inspired by publicly-known sources (KMD, KALRO, TAMSAT, CHIRPS, PlantVillage, Migori County market information). They are **not** fetched live; they are baked into fixtures so the demo is reproducible.

## Why synthetic data is used

1. **Privacy.** Household-level data is sensitive. A real Nyatike household's planting dates, yields, and plot coordinates are personally identifiable information. We do not have consent to use real household records in a public challenge submission.
2. **Reproducibility.** Synthetic fixtures mean a judge or a stranger cloning the repo sees the same Kachieng Ward data every time, without depending on a live API that might rate-limit, change schema, or go down during evaluation.
3. **Honesty.** We do not want to imply that the demo is using live farmer data when it is not.
4. **Safety.** Synthetic data lets us deliberately include edge cases (data gaps, conflicting weather sources, stale calendars, prompt-injection attempts) without affecting real households.

## How real data would be handled in a pilot

In a real pilot at the Nyatike office, the demo fixtures would be replaced with consented data feeds. The data-conduct plan is:

### Consent

- Each household whose plot is included in the system would sign (or thumbprint) a consent form explaining: what data is collected, who can see it, how long it is kept, and how to withdraw.
- Cluster representatives would countersign on behalf of the cluster.
- The consent form would be available in English, Swahili, and Dholuo.

### Privacy

- Household names and phone numbers would be replaced with pseudonymous IDs (`KACH-01-HH-001`, etc.) at the data-collection step.
- Real phone numbers (needed for officer-driven delivery) would be stored in an encrypted column with access restricted to the named officer and supervisor.
- Plot coordinates would be generalised to ~100 m to avoid pinpointing a single household's field.
- The system would never display a real name in any UI surface visible to a viewer role.

### Security

- The database would run on PostgreSQL with role-based access (extension officer, supervisor, viewer) and per-row restrictions where appropriate.
- The application would run behind HTTPS with HSTS, secure cookies, and CSRF protection (already in `config/settings/production.py`).
- Audit logs would be append-only and backed up daily.
- The Ollama model would run on the same host as the application to keep household/plot data within the office's trust boundary.
- No household/plot data would be sent to any external API.

### Withdrawal

- A household can withdraw consent at any time by telling the officer.
- The officer would mark the household as `withdrawn` in the system. The household's plot records would be soft-deleted; the audit trail would still record that the household was once in the system, but no new advisories would reference it.

### Data retention

- Plot records: kept for as long as the household consents; soft-deleted on withdrawal.
- Advisory records: kept for 7 years as part of the office's audit trail (standard Kenyan public-records practice).
- Audit events: kept for 7 years.

### Review

- A county data-protection officer would review the system annually.
- The officer and supervisor would have access to the audit trail at all times.

## Labelling in code and UI

- Every fixture file's name starts with the geographic area (e.g. `migori_kachieng_*`).
- Every household's `notes` field includes "Synthetic household — not a real person." (where present).
- Every cluster's `representative` field starts with "Synthetic rep —".
- The README and the dashboard footer both display the synthetic-data notice.
- This document (`docs/governance/synthetic_data_notice.md`) is the canonical statement.

## What the agent does with the data

- The agent reads household/plot records to compose the advisory prompt.
- The prompt is sent only to the local Ollama model.
- The agent does not send household/plot data to any external API.
- The agent's audit log stores sanitised summaries of tool inputs/outputs (truncated to 800 chars, with prompt-injection phrases stripped).

## What the agent does NOT do with the data

- Does not send it to a hosted LLM API.
- Does not log full household records (only summaries).
- Does not display real names in any UI surface visible to a viewer role.
- Does not persist data outside the application database.
