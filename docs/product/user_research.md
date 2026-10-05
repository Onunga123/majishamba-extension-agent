# User research — Nyatike extension officer (synthetic profile)

> Note: this profile is a composite of publicly-known extension-officer workflows in Kenyan sub-county agricultural offices. No real officer's personal data is used. The named demo officer `nyatike_officer` is a synthetic persona.

## Persona

**Name (synthetic).** Jane Awuor (synthetic).
**Role.** Agricultural Extension Officer, Nyatike Sub-County Agricultural Office.
**Ward assignment.** Kachieng Ward.
**Tenure.** Several years in the office; knows the cluster representatives by first name.
**Phone.** A basic smartphone with SMS, USSD, occasional WhatsApp, occasional web browsing.

## Goals

1. Produce a defensible, sourced planting advisory for each Kachieng cluster at the start of the short-rains season.
2. Show farmers *why* a recommendation was made — citing rainfall, calendar, plot history, pest alerts.
3. Surface data gaps before the advisory is delivered, not after.
4. Keep an audit trail of advisories, approvals and follow-up tasks for the office and the county.
5. Stay in control — never send advice automatically; never let the agent place orders or issue credit flags.

## Frustrations

1. Manually cross-checking rainfall, calendar, plot history, pest alerts and market prices for many households is slow.
2. Pest alerts arrive via WhatsApp and radio without cluster specificity — "fall armyworm in Migori" doesn't tell her which Kachieng cluster is most exposed.
3. She cannot easily reconstruct why she recommended X three months ago — her notes are scattered.
4. Some Kachieng households have no recent plot record on file, and she only discovers this when a farmer challenges the advisory.
5. Generic advice ("plant when it rains") is what climate-smart advisory should *not* be — but it's what the manual process drifts towards under time pressure.

## What she values in MajiShamba

- **Speed.** The agent gathers evidence in seconds; she reviews in minutes.
- **Sourcing.** Every claim has a citation she can show a farmer.
- **Gap visibility.** Missing plot records and stale sources are flagged, not hidden.
- **Approval gate.** The agent stops at DRAFT; she approves before anything is recorded as APPROVED.
- **Follow-up tasks.** After approval, she can create a field visit or cluster meeting task with a deadline.
- **Audit trail.** Every action is logged with her name on it; she can defend her work.

## What she does NOT want

- Auto-sent SMS / USSD.
- Auto-approved advisories.
- Recommendations outside the planting-decision set (no "sell now", no credit).
- A model that overrides her because it's "more confident".

## Scenarios we test against

1. Adequate rainfall + appropriate calendar → plant recommendation. (EVALS Task 1)
2. Below-threshold rainfall onset → delay + local verification. (EVALS Task 2)
3. Fall armyworm alert → pest-monitoring recommendation. (EVALS Task 3)
4. Low maize price → officer reviews marketing options (no auto sell advice). (EVALS Task 4)
5. Missing plot history → data-gap flag + officer follow-up. (EVALS Task 5)
6. Conflicting weather sources → lower confidence, local verification. (EVALS Task 6)
7. Stale calendar source → mark stale, lower confidence. (EVALS Task 7)
8. Action tool called before approval → reject. (EVALS Task 8)
9. Prompt injection in a pest report → ignored. (EVALS Task 9)
10. Model unavailable → deterministic fallback. (EVALS Task 10)

## Pilot notes for real use

In a real pilot at the Nyatike office, the demo fixtures would be replaced with consented household/plot records (see `docs/governance/synthetic_data_notice.md`), and the read-only tool implementations in `apps/mcp_tools/tools.py` would be wired to live KMD/KALRO/market sources under the same Pydantic schemas. The agent, the approval gate, and the audit log would not change.
