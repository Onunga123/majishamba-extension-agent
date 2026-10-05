# Kachieng Ward context — Migori County, Nyatike Sub-County, Kenya

## Geography

**Kachieng Ward** is one of the wards in **Nyatike Sub-County**, **Migori County**, in the former Nyanza Province of western Kenya. The ward lies in the low-to-mid altitude bimodal rainfall zone on the eastern shore of Lake Victoria. Approximate centroid (synthetic, used for the demo): `-0.965, 34.445`.

## Agroclimatic profile

- **Altitude.** Low-to-mid altitude, roughly 1,100–1,300 m above sea level.
- **Rainfall.** Bimodal. Long rains: March–July. Short rains: September–December. Typical annual rainfall in the 800–1,400 mm range.
- **Onset variability.** Short-rains onset is genuinely erratic in this zone; false starts in late September are a known risk. Farmers and extension officers watch for "three consecutive rainy days ≥ 5 mm/day" before planting.
- **Soils.** Mix of sandy, loam, silt-loam and clay patches; sandy plots near the lake plain are common.
- **Drainage.** Low-lying lakeside plots can be water-logged during heavy rains.

## Dominant crops

- **Maize** is the dominant staple and the focus of this MVP.
- Beans, sweet potato, sorghum, cassava and vegetables are also grown but are out of scope for this build.

## Constraints

1. **Erratic rainfall onset.** Late-September false starts cause replanting costs.
2. **Pest pressure.** Fall armyworm (Spodoptera frugiperda) is the major seasonal threat for maize. Storage pests — Larger Grain Borer (Prostephanus truncatus) — matter post-harvest but are out of scope for the planting-advisory MVP.
3. **Market volatility.** Maize prices at Migori Town fluctuate; farmers sometimes sell low immediately after harvest.
4. **Plot records.** The office's household/plot records are partial and out of date; some Kachieng households have no recent season record on file (the KACH-03 fixture reproduces this gap).
5. **Communication.** Most smallholders have a basic phone (SMS/USSD); smartphones are less common. The officer decides delivery channel — MajiShamba does not automate this.

## Why the office's workflow fits this design

The Nyatike Sub-County Agricultural Office's seasonal advisory cycle has four steps:

1. **Pre-season review** — gather rainfall, calendar, plot history, pest alerts, market signals.
2. **Draft advisory** — synthesise into a cluster-specific recommendation.
3. **Officer approval** — confirm, edit, or reject.
4. **Delivery** — share by phone, SMS, USSD, cluster meeting, or printed handout.

MajiShamba automates steps 1 and 2 (agent + MCP tools + open-weights model), keeps step 3 explicitly human (the approval gate), and leaves step 4 entirely to the officer. This is the narrowest useful scope that shows real agentic depth without over-automating.

## Synthetic data fidelity

The synthetic fixtures in `data/fixtures/` reproduce realistic-but-fictional clusters:

- **KACH-01** (Kachieng North, 5 households, 5 plots, lakeside low-lying fields)
- **KACH-02** (Kachieng Central, 6 households, 5 plots, mid-altitude mixed plots, one irrigated)
- **KACH-03** (Kachieng South, 3 households, 2 plots, intentionally sparse plot history — the data-gap test case)

Plot histories for 2022 and 2023 short rains include realistic outcomes: success, partial failure (false rainfall start), delayed planting, high yield on the irrigated plot. Pest alerts and weather signals mirror KALRO / KMD-style bulletins but are clearly labelled as synthetic summaries.

## Sources of inspiration (not live data)

The synthetic fixtures are informed by publicly-known sources in the Kenyan agricultural extension ecosystem:

- Kenya Meteorological Department (KMD)
- Kenya Agricultural and Livestock Research Organization (KALRO)
- TAMSAT (Tropical Applications of Meteorology using SATellite data and ground-based observations)
- CHIRPS (Climate Hazards Group InfraRed Precipitation with Station data)
- PlantVillage (Penn State)
- Migori County market information

No live API is called in the demo. A real pilot would replace the fixture-backed tool implementations with live calls under the same Pydantic schemas.
