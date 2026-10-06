"""KALRO maize guidance adapter — bibliographic metadata only, permission-pending.

The 2021 KCEP-CRAL Maize Extension Manual is © KALRO, all rights reserved.
Public availability is NOT an open-data licence. We do NOT commit the PDF,
do NOT extract passages into the agent's evidence, and do NOT populate a
searchable corpus. See docs/governance/source_access_register.md.

This adapter provides:
- `register_kalro_bibliographic_metadata(...)`: writes a CropCalendar row with
  metadata ONLY (title, ISBN, source URL, publication date). All extraction
  fields are 'not_extracted' / 'metadata_only'. Planting dates, activities,
  onset rules, variety recommendations, fertilizer rules are LEFT NULL/EMPTY.
- `permission_status()`: returns the honest 'permission_pending' state.

The dashboard shows: "Agronomic guidance: permission-pending for KALRO maize
manual ingestion. Bibliographic metadata is recorded; content extraction is
deferred until permission is granted."

We NEVER call a national manual a "KALRO Migori short-rains calendar".
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

logger = logging.getLogger("majishamba.integrations.kalro")


# Statically verified bibliographic record (do not invent details).
KALRO_MAIZE_MANUAL_2021_BIBLIOGRAPHIC = {
    "title": "KCEP-CRAL Integrated Soil Fertility and Water Management Extension Manual",
    "alternative_title": "KENYA Maize Extension Manual",
    "publisher": "Kenya Agricultural and Livestock Research Organization (KALRO)",
    "publication_date": "2021-04",
    "isbn_or_id": "KCEP-CRAL Manual 2021",
    "source_url": "https://statistics.kilimo.go.ke/files/bookpage/KENYA_Maize-Extension-Manual.pdf",
    "alt_source_url": "https://keep.kalro.org/",
    "copyright_notice": "© KALRO 2021. All rights reserved. Reproduction, database storage, and transcription require prior written permission.",
    "disclaimer_note": "KALRO's own disclaimer requires local agro-climatic verification with extension officers.",
    "licence_basis": "© KALRO 2021 — all rights reserved; permission pending",
    "permission_status": "permission_pending",
}


def register_kalro_bibliographic_metadata(
    *,
    crop: str = "maize",
    season: str = "short_rains",
    zone_label: str = "Migori-Low-Mid",
    publication_date: dt.date | None = None,
    actor_id: int | None = None,
) -> dict[str, Any]:
    """Register bibliographic metadata for the KALRO 2021 maize manual.

    No content is extracted. Planting dates and activities are LEFT NULL/EMPTY
    because:
      (a) the manual is national, not a county-specific calendar;
      (b) KALRO © reserve all rights — extraction is permission-pending.

    The dashboard will show: "Local planting dates not specified in this source"
    and "Agronomic guidance: permission-pending for KALRO maize manual ingestion".
    """
    from apps.calendars.models import CropCalendar
    from apps.audit.service import log_audit_event

    pub_date = publication_date or dt.date(2021, 4, 1)
    cc, created = CropCalendar.objects.update_or_create(
        crop=crop, zone_label=zone_label, season=season,
        defaults={
            "source_authority": "KALRO",
            "source_document_id": KALRO_MAIZE_MANUAL_2021_BIBLIOGRAPHIC["isbn_or_id"],
            "product_type": "KCEP-CRAL Maize Extension Manual 2021 (national reference)",
            "publication_date": pub_date,
            "geographic_scope": "national (Kenya)",
            "coverage_level": "national",
            "source_url": KALRO_MAIZE_MANUAL_2021_BIBLIOGRAPHIC["source_url"],
            "licence_or_permission_basis": KALRO_MAIZE_MANUAL_2021_BIBLIOGRAPHIC["licence_basis"],
            "permission_status": CropCalendar.PermissionStatus.PERMISSION_PENDING,
            "synthetic_flag": CropCalendar.SyntheticFlag.REAL,
            "verification_status": CropCalendar.VerificationStatus.BACKGROUND_REFERENCE,
            "extraction_review_status": CropCalendar.ExtractionReviewStatus.NOT_EXTRACTED,
            "local_applicability_review": CropCalendar.LocalApplicabilityReview.NOT_REVIEWED,
            # Crucially: leave planting dates and activities NULL/EMPTY
            "planting_window_start": None,
            "planting_window_end": None,
            "activities": [],
            # Legacy fields
            "source": "KALRO KCEP-CRAL Maize Extension Manual 2021 (bibliographic metadata only; permission-pending)",
            "source_date": pub_date,
        },
    )
    log_audit_event(
        actor_id=actor_id,
        action="ingest:kalro_bibliographic",
        target=cc,
        metadata={
            "isbn_or_id": KALRO_MAIZE_MANUAL_2021_BIBLIOGRAPHIC["isbn_or_id"],
            "permission_status": "permission_pending",
            "extraction_review_status": "not_extracted",
        },
    )
    return {
        "crop_calendar_id": cc.id,
        "created": created,
        "permission_status": cc.permission_status,
        "extraction_review_status": cc.extraction_review_status,
        "planting_window_display": cc.planting_window_display,  # "Local planting dates not specified in this source"
    }


def permission_status() -> dict[str, str]:
    """Return the honest permission-pending state for KALRO content."""
    return {
        "state": "permission_pending",
        "message": "Agronomic guidance: permission-pending for KALRO maize manual ingestion.",
        "bibliographic_recorded": "Bibliographic metadata is recorded (title, publisher, ISBN, source URL, publication date).",
        "extraction_deferred": "Content extraction (planting dates, activities, rules) is deferred until permission is granted.",
        "source_url": KALRO_MAIZE_MANUAL_2021_BIBLIOGRAPHIC["source_url"],
        "licence_basis": KALRO_MAIZE_MANUAL_2021_BIBLIOGRAPHIC["licence_basis"],
        "do_not_label": "KALRO Migori short-rains calendar",  # never call it this
    }
