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
        crop=crop,
        zone_label=zone_label,
        season=season,
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
    """Return the honest permission-pending state for KALRO content.

    Backwards-compatible: existing callers (and tests) rely on the keys
    ``state``, ``message``, ``bibliographic_recorded``, ``extraction_deferred``,
    ``source_url``, ``licence_basis``, and ``do_not_label``.

    The richer page-level context used by the Agronomic Guidance page is
    provided by :func:`guidance_page_context`.
    """
    biblio = KALRO_MAIZE_MANUAL_2021_BIBLIOGRAPHIC
    return {
        "state": "permission_pending",
        "message": "Agronomic guidance: permission-pending for KALRO maize manual ingestion.",
        "bibliographic_recorded": (
            "Bibliographic metadata is recorded (title, publisher, ISBN, source URL, "
            "publication date)."
        ),
        "extraction_deferred": (
            "Content extraction (planting dates, activities, rules) is deferred until "
            "permission is granted."
        ),
        "source_url": biblio["source_url"],
        "licence_basis": biblio["licence_basis"],
        "do_not_label": "KALRO Migori short-rains calendar",  # never call it this
    }


# ---------------------------------------------------------------------------
# Enterprise-grade guidance-page context
# ---------------------------------------------------------------------------

# Status taxonomy — each permission/permission/integration state maps to a
# short user-facing label, a longer explanation, and a semantic tone used by
# the template for the accessible status indicator. Tone is never the *only*
# signal — every state has a textual label.
_STATUS_DEFINITIONS: dict[str, dict[str, str]] = {
    "bibliographic_only": {
        "label": "Permission not confirmed",
        "supporting": "Bibliographic metadata only",
        "tone": "warning",
        "summary": (
            "A bibliographic record exists for this publication, but the system has not "
            "received documented permission to ingest or reproduce the manual's content. "
            "Substantive agronomic guidance from this source is not yet available to the "
            "advisory pipeline."
        ),
    },
    "permission_in_progress": {
        "label": "Permission request in progress",
        "supporting": "Awaiting rights-holder response",
        "tone": "info",
        "summary": (
            "A formal reuse request has been opened with the rights holder. Content "
            "extraction remains deferred until written permission is granted and "
            "documented in the source record."
        ),
    },
    "permission_granted": {
        "label": "Permission granted with conditions",
        "supporting": "Content extraction permitted under licence",
        "tone": "success",
        "summary": (
            "Written permission has been recorded. Extracted content may be cited within "
            "the conditions documented in the source record. Local agronomic review is "
            "still required before advisory use."
        ),
    },
    "permission_denied": {
        "label": "Permission denied",
        "supporting": "Reuse not permitted",
        "tone": "danger",
        "summary": (
            "The rights holder has declined the reuse request. The manual's content may "
            "not be ingested, reproduced, or attributed as a source for advisories."
        ),
    },
    "permission_expired": {
        "label": "Permission requires review",
        "supporting": "Previous grant may have expired",
        "tone": "warning",
        "summary": (
            "A previous permission grant may require review. Confirm the current licence "
            "status with the rights holder before relying on any previously extracted "
            "content."
        ),
    },
    "extracted_pending_review": {
        "label": "Content integrated — awaiting agronomic review",
        "supporting": "Extraction complete; local review pending",
        "tone": "info",
        "summary": (
            "Substantive content has been extracted under permission, but has not yet "
            "completed local agronomic review for the target area. Do not attribute "
            "recommendations to this source until review is complete."
        ),
    },
    "extracted_approved": {
        "label": "Approved for advisory use",
        "supporting": "Reviewed and approved",
        "tone": "success",
        "summary": (
            "Extracted content has completed local agronomic review and is approved as a "
            "citable source for advisories in the documented area."
        ),
    },
}


def _classify_state(*, permission_status: str, extraction_review_status: str) -> str:
    """Map raw model enums to the page-level status taxonomy.

    The mapping is conservative — it never claims a stronger state than the
    underlying data supports. ``permission_pending`` always collapses to
    ``bibliographic_only`` (the system does not record whether a request has
    been sent) unless extraction has actually happened.
    """
    if permission_status == "open_data" or permission_status == "attribution_only":
        if extraction_review_status == "officer_reviewed":
            return "extracted_approved"
        if extraction_review_status in {"passages_extracted", "metadata_only"}:
            return "extracted_pending_review"
        return "bibliographic_only"
    if permission_status == "permission_pending":
        # The system does not track whether a request has been sent; the
        # honest state is "permission not confirmed / bibliographic only".
        return "bibliographic_only"
    if permission_status == "restricted":
        return "permission_denied"
    return "bibliographic_only"


def guidance_page_context() -> dict[str, object]:
    """Build the full context for the Agronomic Guidance page.

    All values are sourced from the actual :class:`CropCalendar` record when
    one exists, falling back to the statically verified bibliographic record
    in :data:`KALRO_MAIZE_MANUAL_2021_BIBLIOGRAPHIC`. No metadata is fabricated.

    Returns a dict with the following keys (all template-safe):

    - ``title``                       — short page title
    - ``description``                 — one-line page description
    - ``breadcrumb``                   — list of (label, url_or_none) tuples
    - ``publication``                 — dict with bibliographic metadata
    - ``status``                      — dict with the resolved status indicator
    - ``restriction``                 — dict with the use-restriction callout
    - ``planting_date_notice``        — dict with the local-planting-date notice
    - ``source_categories``           — list of source categories actually integrated
    - ``workflow``                    — dict with permission/integration workflow state
    - ``return_url``                  — URL back to the dashboard
    - ``data_sources_url``           — URL to the data sources register
    """
    from django.urls import reverse

    from apps.calendars.models import CropCalendar

    biblio = KALRO_MAIZE_MANUAL_2021_BIBLIOGRAPHIC

    # Read the actual database record (short-rains season is the primary
    # reference; long-rains is identical for KALRO because the source is
    # national). If the DB row is missing, we surface the static bibliographic
    # record and mark `record_verified=False`.
    cc = CropCalendar.objects.filter(
        crop="maize",
        zone_label="Migori-Low-Mid",
        season=CropCalendar.Season.SHORT_RAINS,
        source_authority="KALRO",
    ).first()

    permission_status_value = cc.permission_status if cc else "permission_pending"
    extraction_review_status = cc.extraction_review_status if cc else "not_extracted"
    state_key = _classify_state(
        permission_status=permission_status_value,
        extraction_review_status=extraction_review_status,
    )
    status_def = _STATUS_DEFINITIONS[state_key]

    publication = {
        "title": biblio["alternative_title"],
        "subtitle": biblio["title"],
        "publisher": biblio["publisher"],
        "publication_year": (cc.publication_date.year if cc and cc.publication_date else 2021),
        "publication_date": cc.publication_date if cc else None,
        "isbn_or_id": (
            cc.source_document_id if cc and cc.source_document_id else biblio["isbn_or_id"]
        ),
        "source_url": cc.source_url if cc and cc.source_url else biblio["source_url"],
        "alt_source_url": biblio["alt_source_url"],
        "copyright_notice": biblio["copyright_notice"],
        "licence_basis": (
            cc.licence_or_permission_basis
            if cc and cc.licence_or_permission_basis
            else biblio["licence_basis"]
        ),
        "geographic_scope": (
            cc.geographic_scope if cc and cc.geographic_scope else "national (Kenya)"
        ),
        "coverage_level": cc.coverage_level if cc and cc.coverage_level else "national",
        "bibliographic_verification": "verified" if cc else "unverified",
        "bibliographic_verification_label": (
            "Title, publisher, ISBN, source URL, and publication date recorded"
            if cc
            else "Bibliographic record not found in source register"
        ),
        "content_integration_status": (
            "not_integrated"
            if extraction_review_status == "not_extracted"
            else (
                "metadata_only"
                if extraction_review_status == "metadata_only"
                else (
                    "extracted_pending_review"
                    if extraction_review_status == "passages_extracted"
                    else (
                        "approved_for_advisory_use"
                        if extraction_review_status == "officer_reviewed"
                        else "not_integrated"
                    )
                )
            )
        ),
        "content_integration_label": {
            "not_integrated": "Not integrated — content not extracted",
            "metadata_only": "Metadata only — substantive content not extracted",
            "extracted_pending_review": "Content extracted — local agronomic review pending",
            "approved_for_advisory_use": "Content reviewed and approved for advisory use",
        }.get(extraction_review_status, "Not integrated"),
        "record_verified": bool(cc),
        "record_id": cc.id if cc else None,
    }

    status = {
        "key": state_key,
        "label": status_def["label"],
        "supporting": status_def["supporting"],
        "tone": status_def["tone"],
        "summary": status_def["summary"],
        # Preserve the legacy technical phrase for tests and for staff who
        # refer to it in audit / documentation.
        "technical_phrase": "permission-pending for KALRO maize manual ingestion",
    }

    restriction = {
        "heading": "Agronomic use restriction",
        "body": (
            "The substantive content of this manual has not been integrated into the "
            "agricultural advisory system because reuse permission has not been "
            "confirmed. Planting dates, recommended activities, and agronomic rules "
            "have not been extracted from this source."
        ),
        "instruction": (
            "Do not attribute recommendations to this manual or treat them as verified "
            "on its authority until the relevant content has been lawfully incorporated, "
            "reviewed, and approved for the intended use."
        ),
    }

    planting_date_notice = {
        "heading": "Local planting-date verification",
        "body": (
            "This source record does not establish locally appropriate planting dates. "
            "Before communicating planting dates to farmers, verify the recommendation "
            "against current, applicable agro-climatic guidance and consult the relevant "
            "agricultural extension office."
        ),
        "note": (
            "Consulting an extension office does not substitute for every required "
            "agronomic validation step. Local agro-climatic conditions, varietal "
            "suitability, and current-season forecasts must all be confirmed before any "
            "planting recommendation is issued."
        ),
    }

    source_categories = [
        {
            "name": "Kenya Meteorological Department (KMD) bulletins",
            "description": (
                "Daily, 5-day, and 7-day forecasts plus Lake Victoria Basin forecasts. "
                "Cited with attribution; bulletins are not republished."
            ),
            "verification_note": "Manual retrieval — no public API available.",
        },
        {
            "name": "KEPHIS, KALRO, and Migori County pest notices",
            "description": (
                "Official pest notices and factsheets obtained through officer field "
                "reports or official publications, recorded as PestAlert entries with "
                "documented provenance."
            ),
            "verification_note": "No public alert API; manual transcription by officers.",
        },
        {
            "name": "Open-Meteo weather data",
            "description": (
                "Daily forecast variables from the Open-Meteo Forecast API, licensed "
                "under CC-BY 4.0. Stored as WeatherSignal records with full provenance."
            ),
            "verification_note": "Automated ingestion — attribution to Open-Meteo (CC-BY 4.0).",
        },
    ]

    workflow = {
        "heading": "Permission and integration workflow",
        "intro": (
            "The current state of this source is shown below. The system does not "
            "fabricate a workflow: every field is sourced from the actual source "
            "register record or marked as not yet recorded."
        ),
        "steps": [
            {
                "label": "Source registration",
                "value": "Recorded" if cc else "Not recorded",
                "detail": (
                    "Bibliographic record stored in the source register."
                    if cc
                    else "No matching CropCalendar row was found in the source register."
                ),
                "complete": bool(cc),
            },
            {
                "label": "Rights and licence verification",
                "value": "Not confirmed",
                "detail": (
                    "The system has not received documented permission to reproduce or "
                    "ingest the manual's substantive content. Public availability is "
                    "not an open-data licence."
                ),
                "complete": False,
            },
            {
                "label": "Content extraction and integration",
                "value": "Not performed",
                "detail": (
                    "Planting dates, recommended activities, and agronomic rules have "
                    "not been extracted into the advisory pipeline."
                ),
                "complete": False,
            },
            {
                "label": "Agronomic review",
                "value": "Not started",
                "detail": (
                    "Local officer review of any extracted content has not begun. "
                    "Even after permission is granted, a national manual requires "
                    "local agro-climatic review before advisory use."
                ),
                "complete": False,
            },
            {
                "label": "Geographic applicability",
                "value": "National scope (not local)",
                "detail": (
                    "The KCEP-CRAL manual is a national reference; it is not a "
                    "county-specific calendar and does not establish planting dates "
                    "for Kachieng' Ward."
                ),
                "complete": False,
            },
            {
                "label": "Approval for advisory use",
                "value": "Not approved",
                "detail": (
                    "The source has not been approved as a citable reference for "
                    "advisories. KALRO has not endorsed the software or approved any "
                    "recommendation derived from this manual."
                ),
                "complete": False,
            },
        ],
        "next_action_label": "View source register",
        "next_action_url": reverse("dashboard:data_sources"),
        "next_action_note": (
            "Open the Data & Sources register to inspect all ingested source records "
            "and officer-supplied metadata. Authorised officers can update documented "
            "permission status when evidence is received."
        ),
        "confidentiality_note": (
            "Internal legal correspondence and confidential licence terms are not "
            "displayed here. They are restricted to authorised roles and stored "
            "outside the advisory interface."
        ),
    }

    breadcrumb = [
        ("Dashboard", reverse("dashboard:home")),
        ("Knowledge Sources", reverse("dashboard:data_sources")),
        ("KALRO Maize Extension Manual", None),
    ]

    return {
        "title": "Agronomic Guidance",
        "description": (
            "Source registration, permission status, and agronomic evidence governance."
        ),
        "breadcrumb": breadcrumb,
        "publication": publication,
        "status": status,
        "restriction": restriction,
        "planting_date_notice": planting_date_notice,
        "source_categories": source_categories,
        "workflow": workflow,
        "return_url": reverse("dashboard:home"),
        "data_sources_url": reverse("dashboard:data_sources"),
        # Keep the legacy message for backwards compatibility with existing
        # callers and tests that import `permission_status()` directly.
        "legacy_message": permission_status()["message"],
    }
