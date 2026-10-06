"""Pest notice adapter — official notices, officer field reports, synthetic test scenarios.

Honest availability states (see docs/governance/source_access_register.md):
- No public pest-alert API exists for KEPHIS, KALRO, or Migori County.
- A KALRO pest factsheet is BACKGROUND guidance, NOT a current outbreak in Kachieng.
- We do NOT assign 'High' severity if the source merely mentions the pest.
- We do NOT treat regional reports as confirmed infestation of all 14 localities.
- Default state: "No current verified official pest notice available for this area."
- We NEVER say "No pest risk" — that would falsely claim pests are absent.

This adapter provides:
- `ingest_officer_field_report(...)`: writes a PestAlert row from an authorized
  officer's verified local observation. Required fields: officer_author_name,
  observation_date, coverage, pest, crop.
- `ingest_published_notice_metadata(...)`: writes a PestAlert row from an official
  notice (e.g. KEPHIS alert, county agricultural report). The officer must have
  manually verified the notice and transcribe its metadata accurately.
- `no_current_pest_notice()`: returns the honest default state for the dashboard.

We do NOT automatically scrape pest notices because:
  (a) No public API/RSS feed exists,
  (b) Pest notices are published as ad-hoc announcements,
  (c) We respect service terms and do not bulk-download.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

logger = logging.getLogger("majishamba.integrations.pests")


def ingest_officer_field_report(
    *,
    officer_author_name: str,
    observation_date: dt.date,
    coverage: str,  # e.g. "Kachieng Ward"
    coverage_level: str,  # e.g. "ward" or "locality"
    pest: str,
    crop: str = "maize",
    severity: str = "not_specified",  # officer must NOT inflate; default "not_specified"
    advisory: str = "",
    county: str = "Migori",
    region: str = "Nyanza",
    actor_id: int | None = None,
) -> dict[str, Any]:
    """Ingest an officer's verified local field report.

    The officer is the named authority for this record. It is labelled
    `verification_status = officer_field_report`, NOT as a KEPHIS/KALRO publication.
    """
    from apps.pests.models import PestAlert
    from apps.audit.service import log_audit_event

    if not officer_author_name:
        raise ValueError("officer_author_name is required for an officer field report")
    if not observation_date:
        raise ValueError("observation_date is required for an officer field report")

    alert = PestAlert.objects.create(
        crop=crop,
        pest=pest,
        county=county,
        region=region,
        severity=severity,
        advisory=advisory,
        # Provenance — officer field report
        source_authority=f"Officer field report — {officer_author_name}",
        product_type="Officer field report",
        publication_date=observation_date,
        observed_from=observation_date,
        observed_to=observation_date,
        geographic_scope=coverage,
        coverage_level=coverage_level,
        officer_author_name=officer_author_name,
        # Legacy fields
        source=f"Officer field report — {officer_author_name}",
        source_date=observation_date,
        # Honest flags
        synthetic_flag=PestAlert.SyntheticFlag.OFFICER_REPORT,
        verification_status=PestAlert.VerificationStatus.OFFICER_FIELD_REPORT,
        permission_status=PestAlert.PermissionStatus.OPEN_DATA,  # officer's own report
        extraction_review_status=PestAlert.ExtractionReviewStatus.OFFICER_REVIEWED,
    )
    log_audit_event(
        actor_id=actor_id,
        action="ingest:officer_pest_report",
        target=alert,
        metadata={
            "officer_author_name": officer_author_name,
            "observation_date": observation_date.isoformat() if observation_date else None,
            "coverage": coverage,
            "pest": pest,
            "crop": crop,
        },
    )
    return {"pest_alert_id": alert.id, "verification_status": alert.verification_status}


def ingest_published_notice_metadata(
    *,
    authority: str,  # e.g. "KEPHIS", "Migori County Department of Agriculture"
    product_type: str,  # e.g. "Pest alert notice", "County agricultural report"
    publication_date: dt.date,
    pest: str,
    crop: str = "maize",
    severity: str = "not_specified",
    severity_as_published: str = "",  # exact text from the source, e.g. "outbreak reported"
    advisory: str = "",
    geographic_scope: str = "",
    coverage_level: str = "county",
    source_url: str = "",
    source_document_id: str = "",
    valid_from: dt.date | None = None,
    valid_to: dt.date | None = None,
    actor_id: int | None = None,
) -> dict[str, Any]:
    """Ingest metadata about a published official pest notice (KEPHIS, county report, etc.).

    The officer must have manually verified the notice and transcribe its metadata
    accurately. We do NOT scrape. Severity is stored EXACTLY as published; if the
    source does not state severity, leave it as 'not_specified' (do NOT inflate).
    """
    from apps.pests.models import PestAlert
    from apps.audit.service import log_audit_event

    if severity_as_published and not severity:
        # Officer provides the exact text from the source; we keep that as a separate
        # field. The structured `severity` field stays "not_specified" unless the
        # officer explicitly maps the published text to one of our Severity choices.
        pass

    alert = PestAlert.objects.create(
        crop=crop,
        pest=pest,
        county="Migori",
        region="Nyanza",
        severity=severity,
        advisory=advisory,
        # Provenance
        source_authority=authority,
        source_document_id=source_document_id,
        product_type=product_type,
        publication_date=publication_date,
        valid_from=valid_from,
        valid_to=valid_to,
        geographic_scope=geographic_scope,
        coverage_level=coverage_level,
        source_url=source_url,
        # Legacy fields
        source=f"{authority} {product_type}",
        source_date=publication_date,
        # Honest flags
        synthetic_flag=PestAlert.SyntheticFlag.REAL,
        verification_status=PestAlert.VerificationStatus.CURRENT_OFFICIAL,
        permission_status=PestAlert.PermissionStatus.ATTRIBUTION_ONLY,
        extraction_review_status=PestAlert.ExtractionReviewStatus.METADATA_ONLY,
    )
    log_audit_event(
        actor_id=actor_id,
        action="ingest:published_pest_notice",
        target=alert,
        metadata={
            "authority": authority,
            "product_type": product_type,
            "publication_date": publication_date.isoformat() if publication_date else None,
            "pest": pest,
            "crop": crop,
            "severity": severity,
        },
    )
    return {"pest_alert_id": alert.id, "verification_status": alert.verification_status}


def ingest_kalro_factsheet_metadata(
    *,
    publication_date: dt.date,
    pest: str,
    crop: str = "maize",
    factsheet_url: str = "",
    factsheet_id: str = "",
    actor_id: int | None = None,
) -> dict[str, Any]:
    """Ingest metadata about a KALRO pest factsheet.

    A KALRO factsheet is BACKGROUND guidance, NOT a current outbreak.
    severity stays 'not_specified' (we do not infer outbreak severity from a factsheet).
    verification_status = background_reference.
    """
    from apps.pests.models import PestAlert
    from apps.audit.service import log_audit_event

    alert = PestAlert.objects.create(
        crop=crop,
        pest=pest,
        county="Migori",
        region="Nyanza",
        severity=PestAlert.Severity.NOT_SPECIFIED,
        advisory="",  # do NOT extract factsheet text — KALRO © reserve all rights
        # Provenance
        source_authority="KALRO",
        source_document_id=factsheet_id,
        product_type="Pest factsheet (background reference)",
        publication_date=publication_date,
        geographic_scope="national",
        coverage_level="national",
        source_url=factsheet_url,
        # Legacy fields
        source="KALRO pest factsheet (background reference)",
        source_date=publication_date,
        # Honest flags
        synthetic_flag=PestAlert.SyntheticFlag.REAL,
        verification_status=PestAlert.VerificationStatus.BACKGROUND_REFERENCE,
        permission_status=PestAlert.PermissionStatus.PERMISSION_PENDING,
        extraction_review_status=PestAlert.ExtractionReviewStatus.NOT_EXTRACTED,
    )
    log_audit_event(
        actor_id=actor_id,
        action="ingest:kalro_factsheet",
        target=alert,
        metadata={"pest": pest, "crop": crop, "factsheet_id": factsheet_id},
    )
    return {"pest_alert_id": alert.id, "verification_status": alert.verification_status}


def no_current_pest_notice() -> dict[str, str]:
    """Return the honest default state for the dashboard."""
    return {
        "state": "no_current_notice",
        "message": "No current verified official pest notice available for this area.",
        "scouting_note": "This does not establish that pests are absent. Local scouting and extension-officer verification remain necessary.",
        "do_not_display": "No pest risk",  # explicitly listed; we never show this
    }
