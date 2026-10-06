"""KMD (Kenya Meteorological Department) provider adapter.

Honest availability states (see docs/governance/source_access_register.md):
- KMD has NO public API.
- Products are published as web pages + PDFs on https://meteo.go.ke/our-products/.
- The smallest geographic unit is county-level (not ward or locality).
- Lake Victoria forecasts cover the Lake Victoria Basin (regional, includes Migori).
- We do NOT interpolate locality-level rainfall or onset from regional prose.
- We do NOT republish bulletin text — we record metadata + link to the official page.

This adapter provides:
- `discover_kmd_products()`: returns the known product catalogue (statically defined
  based on the public KMD website). This is NOT a live discovery — it's the manually
  verified list of products KMD publishes, used to populate the source-access register
  and to give the officer a starting point.
- `ingest_kmd_bulletin_metadata(**fields)`: writes a WeatherSignal row from
  officer-supplied metadata about a KMD bulletin (after the officer has manually
  read the bulletin on the KMD website). This is the "manual retrieval" path.

We do NOT automatically fetch bulletins because:
  (a) KMD has no API,
  (b) prefetching/bulk-downloading is forbidden by the OSM-style service terms,
  (c) we respect robots directives and reasonable rate limits.

The honest default state for KMD weather in the dashboard is:
- "No current verified KMD bulletin has been ingested for this area."
- "Manual retrieval is required. Visit https://meteo.go.ke/our-products/."

The officer can then read the bulletin and use the ingest_kmd_bulletin_metadata()
helper (or the future officer upload form) to record a WeatherSignal with
verification_status = current_official or regional_context.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

logger = logging.getLogger("majishamba.integrations.kmd")


# The KMD product catalogue — manually verified from the public KMD website
# (https://meteo.go.ke/our-products/, last inspected 2026-10-05). This is NOT
# a live API response; it is the static list of products KMD publishes.
# We document it so the officer knows what to look for on the KMD site.
KMD_PRODUCT_CATALOGUE: list[dict[str, str]] = [
    {
        "product_type": "Daily Forecast",
        "coverage_level": "national",
        "geographic_scope": "Kenya",
        "publication_frequency": "daily",
        "source_url": "https://meteo.go.ke/our-products/daily-forecast",
        "notes": "National daily weather forecast. County-level breakdowns available on the County Forecasts page.",
    },
    {
        "product_type": "5 Days Forecast",
        "coverage_level": "national",
        "geographic_scope": "Kenya",
        "publication_frequency": "every 5 days",
        "source_url": "https://meteo.go.ke/our-products/5-days-forecast",
        "notes": "National 5-day weather forecast.",
    },
    {
        "product_type": "7 Days Forecast",
        "coverage_level": "national",
        "geographic_scope": "Kenya",
        "publication_frequency": "every 7 days",
        "source_url": "https://meteo.go.ke/our-products/7-days-forecast",
        "notes": "National 7-day weather forecast. KMD publishes a downloadable PDF.",
    },
    {
        "product_type": "County Forecast",
        "coverage_level": "county",
        "geographic_scope": "Migori County (and 46 other counties)",
        "publication_frequency": "daily",
        "source_url": "https://meteo.go.ke/our-products/county-forecasts",
        "notes": "Per-county forecast. Migori County forecast is the most geographically specific KMD product applicable to Kachieng Ward.",
    },
    {
        "product_type": "Lake Victoria Fishing Forecast",
        "coverage_level": "regional",
        "geographic_scope": "Lake Victoria Basin (includes Migori)",
        "publication_frequency": "daily",
        "source_url": "https://meteo.go.ke/our-products/",
        "notes": "Regional forecast for the Lake Victoria Basin. Covers Migori as part of the basin, not as a Nyatike station observation.",
    },
    {
        "product_type": "Seasonal Outlook",
        "coverage_level": "national",
        "geographic_scope": "Kenya",
        "publication_frequency": "per rain season",
        "source_url": "https://meteo.go.ke/our-products/",
        "notes": "Monthly or per-season outlook. Less geographically specific than county forecasts.",
    },
]


def discover_kmd_products() -> list[dict[str, str]]:
    """Return the statically-verified KMD product catalogue.

    This is NOT a live API call — KMD has no public API.
    The list is manually maintained based on the public KMD website.
    """
    return list(KMD_PRODUCT_CATALOGUE)


def ingest_kmd_bulletin_metadata(
    *,
    area_label: str,
    period: str,
    product_type: str,
    publication_date: dt.date,
    valid_from: dt.date | None = None,
    valid_to: dt.date | None = None,
    geographic_scope: str = "",
    coverage_level: str = "county",
    forecast_summary: str = "",
    rainfall_mm: float | None = None,
    rainfall_units: str = "mm",
    rainfall_period_note: str = "",
    onset_status: str = "unknown",
    confidence: str = "medium",
    source_url: str = "",
    sub_county_id: int | None = None,
    actor_id: int | None = None,
) -> dict[str, Any]:
    """Ingest metadata about a KMD bulletin that an officer has manually read.

    The officer is responsible for transcribing the bulletin's metadata accurately.
    We do NOT fetch the bulletin ourselves (no public API; respect robots/rate-limits).

    Returns the created WeatherSignal as a dict.
    """
    from apps.weather.models import WeatherSignal
    from apps.audit.service import log_audit_event

    if rainfall_mm is not None and not rainfall_period_note:
        raise ValueError(
            "rainfall_period_note is required when rainfall_mm is set — "
            "numeric rainfall must record the period and geographic scope it applies to."
        )

    # Determine honest verification_status based on coverage_level.
    # Regional forecasts (Lake Victoria Basin) are NOT county-specific.
    if coverage_level == "regional":
        verification_status = WeatherSignal.VerificationStatus.REGIONAL_CONTEXT
    elif coverage_level == "county":
        verification_status = WeatherSignal.VerificationStatus.CURRENT_OFFICIAL
    else:
        verification_status = WeatherSignal.VerificationStatus.CURRENT_OFFICIAL

    sig = WeatherSignal.objects.create(
        sub_county_id=sub_county_id,
        area_label=area_label,
        period=period,
        rainfall_mm=rainfall_mm,
        rainfall_units=rainfall_units,
        rainfall_period_note=rainfall_period_note,
        forecast_summary=forecast_summary,
        onset_status=onset_status,
        confidence=confidence,
        # Provenance
        source_authority="Kenya Meteorological Department",
        product_type=product_type,
        publication_date=publication_date,
        valid_from=valid_from,
        valid_to=valid_to,
        geographic_scope=geographic_scope,
        coverage_level=coverage_level,
        source_url=source_url,
        # Legacy fields (for backwards-compat)
        source=f"KMD {product_type}",
        source_date=publication_date,
        # Honest flags
        synthetic_flag=WeatherSignal.SyntheticFlag.REAL,
        verification_status=verification_status,
        permission_status=WeatherSignal.PermissionStatus.ATTRIBUTION_ONLY,
        extraction_review_status=WeatherSignal.ExtractionReviewStatus.METADATA_ONLY,
    )
    log_audit_event(
        actor_id=actor_id,
        action="ingest:kmd_bulletin",
        target=sig,
        metadata={
            "product_type": product_type,
            "publication_date": publication_date.isoformat() if publication_date else None,
            "coverage_level": coverage_level,
            "geographic_scope": geographic_scope,
        },
    )
    return {
        "weather_signal_id": sig.id,
        "verification_status": sig.verification_status,
        "display_label": sig.display_label,
    }


def no_current_kmd_notice() -> dict[str, str]:
    """Return the honest default state for the dashboard when no KMD bulletin
    has been ingested for an area."""
    return {
        "state": "no_current_notice",
        "message": "No current verified KMD bulletin has been ingested for this area.",
        "manual_retrieval_note": "Manual retrieval is required. Visit https://meteo.go.ke/our-products/ (County Forecasts for Migori, or the 7 Days Forecast).",
        "do_not_display": "No pest risk",  # explicitly listed to make sure we never say this
    }
