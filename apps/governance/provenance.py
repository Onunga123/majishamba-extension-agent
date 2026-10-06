"""Provenance mixin for source-attributed evidence records.

Shared fields used by WeatherSignal, PestAlert, and CropCalendar to record
the full chain of evidence from an official publication to a stored record.

Distinguishes:
- publication_date      — when the authority issued the document
- observed_from / observed_to — the observation period (for station data)
- valid_from / valid_to — the forecast validity period (for forecasts)
- retrieved_at          — when the system retrieved the document
- last_checked_at       — when the system last checked for a new edition

Reference manuals do not auto-expire after an arbitrary two-year threshold;
their `is_stale` logic is governed by edition/supersession, not publication date.
"""
from __future__ import annotations

from django.db import models


class ProvenanceMixin(models.Model):
    """Abstract base with provenance fields shared across evidence models.

    Concrete models use this as a mixin via multiple inheritance with
    `models.Model` and add their own domain-specific fields.
    """

    class SyntheticFlag(models.TextChoices):
        REAL = "real", "Real (sourced from official publication)"
        SYNTHETIC = "synthetic", "Synthetic test scenario"
        OFFICER_REPORT = "officer_report", "Officer field report"

    class VerificationStatus(models.TextChoices):
        CURRENT_OFFICIAL = "current_official", "Current official bulletin"
        REGIONAL_CONTEXT = "regional_context", "Regional context"
        BACKGROUND_REFERENCE = "background_reference", "Background reference (not current outbreak)"
        OFFICER_FIELD_REPORT = "officer_field_report", "Officer field report"
        HISTORICAL = "historical", "Historical notice (no longer current)"
        SYNTHETIC = "synthetic", "Synthetic test scenario"
        NO_CURRENT_NOTICE = "no_current_notice", "No current notice available"

    class PermissionStatus(models.TextChoices):
        OPEN_DATA = "open_data", "Open data (clearly reusable licence)"
        ATTRIBUTION_ONLY = "attribution_only", "Public; cite with attribution"
        PERMISSION_PENDING = "permission_pending", "Permission pending"
        RESTRICTED = "restricted", "Restricted (do not reproduce)"

    class ExtractionReviewStatus(models.TextChoices):
        NOT_EXTRACTED = "not_extracted", "Not extracted (metadata only)"
        METADATA_ONLY = "metadata_only", "Metadata only"
        PASSAGES_EXTRACTED = "passages_extracted", "Passages extracted under licence"
        OFFICER_REVIEWED = "officer_reviewed", "Officer reviewed"

    # --- Source authority ---------------------------------------------------
    source_authority = models.CharField(
        max_length=120, blank=True,
        help_text="Issuing authority, e.g. 'Kenya Meteorological Department', 'KALRO', 'KEPHIS', 'Officer field report'.",
    )
    source_document_id = models.CharField(
        max_length=120, blank=True,
        help_text="Document/notice ID assigned by the authority, if known.",
    )
    product_type = models.CharField(
        max_length=80, blank=True,
        help_text="Authority's product name, e.g. '7 Days Forecast', 'KCEP-CRAL Maize Extension Manual', 'Pest factsheet', 'Officer field report'.",
    )

    # --- Dates (publication, observation, validity, retrieval) -------------
    publication_date = models.DateField(null=True, blank=True, help_text="When the authority issued the document.")
    observed_from = models.DateField(null=True, blank=True, help_text="Start of the observation period (for station data).")
    observed_to = models.DateField(null=True, blank=True, help_text="End of the observation period (for station data).")
    valid_from = models.DateField(null=True, blank=True, help_text="Forecast validity start (for forecasts).")
    valid_to = models.DateField(null=True, blank=True, help_text="Forecast validity end (for forecasts).")
    last_checked_at = models.DateTimeField(null=True, blank=True, help_text="When the system last checked for a new edition.")

    # --- Geographic scope --------------------------------------------------
    geographic_scope = models.CharField(
        max_length=160, blank=True,
        help_text="Free-text scope label as published, e.g. 'Lake Victoria Basin', 'Migori County', 'national'.",
    )
    coverage_level = models.CharField(
        max_length=40, blank=True,
        help_text="One of: 'national', 'regional', 'county', 'sub-county', 'ward', 'locality', 'point'.",
    )

    # --- Provenance + integrity -------------------------------------------
    raw_document_checksum = models.CharField(max_length=128, blank=True, help_text="SHA-256 of the source document, if stored.")
    extraction_version = models.CharField(max_length=40, blank=True, help_text="Extraction code version used to ingest.")
    evidence_passage_reference = models.CharField(
        max_length=200, blank=True,
        help_text="Page/section reference for the supporting passage, e.g. 'p. 17, section 3.2'.",
    )
    licence_or_permission_basis = models.CharField(
        max_length=200, blank=True,
        help_text="Basis for reuse, e.g. '© KALRO 2021 — all rights reserved; permission pending', 'MIT licence', 'Public; cite with attribution'.",
    )
    permission_status = models.CharField(
        max_length=40, choices=PermissionStatus.choices, default=PermissionStatus.ATTRIBUTION_ONLY,
    )
    synthetic_flag = models.CharField(
        max_length=40, choices=SyntheticFlag.choices, default=SyntheticFlag.SYNTHETIC,
        help_text="Synthetic records are kept for tests/demo and are never relabelled as real.",
    )
    verification_status = models.CharField(
        max_length=40, choices=VerificationStatus.choices, default=VerificationStatus.SYNTHETIC,
        help_text="Honest availability state — see docs/governance/source_access_register.md.",
    )
    extraction_review_status = models.CharField(
        max_length=40, choices=ExtractionReviewStatus.choices, default=ExtractionReviewStatus.NOT_EXTRACTED,
    )

    class Meta:
        abstract = True

    @property
    def is_synthetic(self) -> bool:
        return self.synthetic_flag == self.SyntheticFlag.SYNTHETIC

    @property
    def is_officer_report(self) -> bool:
        return self.synthetic_flag == self.SyntheticFlag.OFFICER_REPORT

    @property
    def is_current_official(self) -> bool:
        return self.verification_status == self.VerificationStatus.CURRENT_OFFICIAL

    @property
    def is_regional_context(self) -> bool:
        return self.verification_status == self.VerificationStatus.REGIONAL_CONTEXT

    @property
    def is_no_current_notice(self) -> bool:
        return self.verification_status == self.VerificationStatus.NO_CURRENT_NOTICE

    @property
    def is_permission_pending(self) -> bool:
        return self.permission_status == self.PermissionStatus.PERMISSION_PENDING

    @property
    def display_label(self) -> str:
        """Short human-readable label for the dashboard."""
        if self.is_no_current_notice:
            return "No current verified notice"
        if self.is_officer_report:
            return f"Officer field report — {self.source_authority}"
        if self.is_regional_context:
            return f"Regional context — {self.geographic_scope or self.source_authority}"
        if self.is_current_official:
            return f"{self.product_type or self.source_authority}"
        if self.is_synthetic:
            return "Synthetic test scenario"
        return f"{self.source_authority} — {self.product_type}"
