# Problem statement — Kachieng AI Agent

## The institution

The Nyatike Sub-County Agricultural Office is part of the Migori County agricultural extension system, serving smallholder farmers in Nyatike Sub-County. The office's named officer is responsible for translating seasonal agronomic signals into planting advisories for farmer clusters in Kachieng Ward.

## The problem

Each season, the Nyatike officer must compare:

- **Rainfall forecasts** from the Kenya Meteorological Department (KMD) and rainfall-estimate products (CHIRPS, TAMSAT).
- **Crop calendars** published by KALRO and the county government, which pin the recommended planting window for short-rains maize in the Migori low-to-mid altitude bimodal zone.
- **Plot histories** — what each household planted in prior seasons, the planting date, the outcome (success / partial failure / total failure / delayed planting), and the yield band.
- **Pest alerts** arriving via WhatsApp groups, radio, KALRO bulletins, and PlantVillage — without cluster specificity.
- **Market prices** at Migori Town and nearby markets — useful for the officer to anticipate farmer marketing questions and to avoid advisory conflicts.

This comparison is manual. The officer reads each source, mentally weighs them, and produces a written advisory that is shared by phone, SMS, USSD, cluster meeting, or printed handout. The cycle has several known weaknesses:

- **Erratic rainfall onset.** Short-rains onset in Nyatike is genuinely erratic; false starts in late September cause crop failure or replanting costs for Kachieng households who planted too early.
- **Pest alerts without cluster specificity.** A fall armyworm alert for "Migori" applies to all clusters in principle, but the officer has no automated way to ask "which of KACH-01 / KACH-02 / KACH-03 is most exposed right now?"
- **No explanation trail.** When a farmer asks "why should I wait?", the officer has to reconstruct the reasoning from memory or from scattered notes; there is no audit trail that links the advisory to its evidence.
- **Data gaps are invisible.** If a household has no recent plot history in the office's records, the officer may not notice until the advisory is delivered and a farmer challenges it.
- **Generic advice.** The combination of the above pushes the officer towards generic advice ("plant when it rains") which is precisely the opposite of what climate-smart advisory should be.

## Why an agent helps

An agent that can call structured tools, gather the evidence in seconds, draft a defensible advisory, and then **stop** for officer review is a multiplier for the officer — not a replacement. The officer still decides what is sent, to whom, and how. The agent's value is:

1. Speed: gather evidence in seconds.
2. Sourcing: every claim has a citation.
3. Gaps are visible: missing plot records, stale calendar sources, conflicting weather signals are surfaced, not hidden.
4. Consistency: the same workflow every time, with an audit trail.

## What we deliberately do not solve

- SMS / USSD dispatch. The officer decides delivery channel.
- Credit scoring for inputs.
- Multi-crop calendars. MVP is maize, short rains.
- Multi-county support. MVP is Migori → Nyatike → Kachieng.
- Full post-harvest traceability.
- Automated re-runs. The officer triggers each run.

Keeping the scope narrow and deep lets us show strong agentic depth (LangGraph + 8 MCP tools + open-weights model + human gate) without overpromising.
