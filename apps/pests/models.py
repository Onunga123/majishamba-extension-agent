"""Pest alert models — official notices, officer field reports, and synthetic test scenarios.

Categories (see docs/governance/source_access_register.md):
- Official outbreak/pest notice        — verification_status = current_official
- Verified county/extension field report — verification_status = officer_field_report
- General pest reference              — verification_status = background_reference
- Historical notice                    — verification_status = historical
- Synthetic evaluation scenario        — synthetic_flag = synthetic

If no current applicable official notice is found, the dashboard shows
"No current verified official pest notice available for this area."
This does NOT establish that pests are absent.
"""
from __future__ import annotations

from django.db import models

from apps.governance.provenance import ProvenanceMixin


class PestAlert(ProvenanceMixin):
    """A pest notice, field report, or synthetic test scenario.

    ProvenanceMixin adds: source_authority, source_document_id, product_type,
    publication_date, observed_from/observed_to, valid_from/valid_to,
    geographic_scope, coverage_level, last_checked_at, raw_document_checksum,
    extraction_version, evidence_passage_reference, licence_or_permission_basis,
    permission_status, synthetic_flag, verification_status, extraction_review_status.
    """

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MODERATE = "moderate", "Moderate"
        HIGH = "high", "High"
        EXTREME = "extreme", "Extreme"
        NOT_SPECIFIED = "not_specified", "Not specified"

    crop = models.CharField(max_length=80, default="maize")
    pest = models.CharField(max_length=120)
    county = models.CharField(max_length=80, default="Migori")
    region = models.CharField(max_length=120, default="Nyanza")
    severity = models.CharField(
        max_length=20, choices=Severity.choices, default=Severity.NOT_SPECIFIED,
        help_text="Severity EXACTLY as published. Do NOT assign 'High' if the source merely mentions the pest. Default 'not_specified' until an authority states a severity.",
    )
    advisory = models.TextField(blank=True, help_text="Supporting passage or summary, ONLY if licence permits. Otherwise leave blank and link to source.")
    # Legacy fields
    source = models.CharField(max_length=160, blank=True)
    source_url = models.URLField(blank=True)
    source_date = models.DateField(null=True, blank=True, help_text="Legacy alias for publication_date.")
    retrieved_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    # Author of an officer field report (only set when synthetic_flag = officer_report).
    officer_author_name = models.CharField(
        max_length=160, blank=True,
        help_text="Author of an officer field report. Required if synthetic_flag=officer_report.",
    )

    class Meta:
        ordering = ("-publication_date", "-source_date", "-retrieved_at")

    @property
    def effective_publication_date(self):
        return self.publication_date or self.source_date

    @property
    def severity_display_safe(self) -> str:
        """Show severity only when actually set; never show 'Not specified' as if it were a real classification."""
        if self.severity == self.Severity.NOT_SPECIFIED:
            return "Severity not stated in source"
        return self.get_severity_display()

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.pest} ({self.severity_display_safe}) — {self.county} {self.effective_publication_date}"
