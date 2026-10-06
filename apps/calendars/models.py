"""Crop calendar models — bibliographic metadata only for KALRO maize guidance.

KALRO's 2021 KCEP-CRAL Maize Extension Manual is © KALRO, all rights reserved.
Public availability is NOT an open-data licence. We do NOT commit the PDF,
do NOT extract passages into evidence, and do NOT populate a searchable corpus
until permission is granted. See docs/governance/source_access_register.md.

The model represents a calendar entry with full provenance, including:
- source_authority (e.g. 'KALRO')
- product_type (e.g. 'KCEP-CRAL Maize Extension Manual 2021')
- licence_or_permission_basis
- permission_status (open_data | attribution_only | permission_pending | restricted)
- extraction_review_status (not_extracted | metadata_only | passages_extracted | officer_reviewed)

Reference manuals do NOT auto-expire after an arbitrary two-year threshold.
is_stale logic is governed by edition/supersession and local review, not by
publication date alone.
"""
from __future__ import annotations

import datetime as dt

from django.db import models

from apps.geography.models import AgroClimaticZone
from apps.governance.provenance import ProvenanceMixin


class CropCalendar(ProvenanceMixin):
    """Bibliographic metadata + (if permission granted) conditionally-extracted guidance.

    ProvenanceMixin adds: source_authority, source_document_id, product_type,
    publication_date, observed_from/observed_to, valid_from/valid_to,
    geographic_scope, coverage_level, last_checked_at, raw_document_checksum,
    extraction_version, evidence_passage_reference, licence_or_permission_basis,
    permission_status, synthetic_flag, verification_status, extraction_review_status.
    """

    class Season(models.TextChoices):
        SHORT_RAINS = "short_rains", "Short rains (Sep–Dec)"
        LONG_RAINS = "long_rains", "Long rains (Mar–Jul)"

    class LocalApplicabilityReview(models.TextChoices):
        NOT_REVIEWED = "not_reviewed", "Not reviewed by local officer"
        REVIEWED = "reviewed", "Reviewed by local officer"
        REJECTED = "rejected", "Reviewed and rejected for this area"

    crop = models.CharField(max_length=80, default="maize")
    zone = models.ForeignKey(
        AgroClimaticZone,
        on_delete=models.PROTECT,
        related_name="calendars",
        null=True,
        blank=True,
    )
    zone_label = models.CharField(
        max_length=120,
        blank=True,
        help_text="Free-text zone label used when zone FK is not present (e.g. 'Migori-Low-Mid').",
    )
    season = models.CharField(max_length=40, choices=Season.choices, default=Season.SHORT_RAINS)
    # Planting window — left NULL when the source does not specify local dates.
    # Do NOT invent dates from a national manual (national is not local).
    planting_window_start = models.DateField(
        null=True, blank=True,
        help_text="Planting window start. Leave NULL when the source does not specify LOCAL dates for this zone.",
    )
    planting_window_end = models.DateField(
        null=True, blank=True,
        help_text="Planting window end. Leave NULL when the source does not specify LOCAL dates for this zone.",
    )
    activities = models.JSONField(
        default=list,
        help_text="Ordered list of recommended activities. Store ONLY if licence permits reproduction. Otherwise leave empty.",
    )
    # Legacy fields
    source = models.CharField(max_length=160, blank=True)
    source_url = models.URLField(blank=True)
    source_date = models.DateField(null=True, blank=True, help_text="Legacy alias for publication_date.")
    # Local-applicability review (separate from extraction_review_status):
    # even a permissibly-extracted national manual needs local officer review before
    # being treated as locally applicable.
    local_applicability_review = models.CharField(
        max_length=40, choices=LocalApplicabilityReview.choices, default=LocalApplicabilityReview.NOT_REVIEWED,
    )

    class Meta:
        ordering = ("-publication_date", "-source_date")
        unique_together = ("crop", "zone_label", "season")

    def is_stale(self, *, as_of: dt.date | None = None, max_age_days: int | None = None) -> bool:
        """Reference manuals do NOT auto-expire by date.

        Staleness is governed by edition/supersession, not by publication date.
        For backwards-compat, callers that pass `max_age_days` get the old
        date-based check; otherwise we return False (manuals are not stale by age).
        """
        if max_age_days is None:
            # Reference manuals: never stale by age alone.
            return False
        as_of = as_of or dt.date.today()
        pub = self.effective_publication_date
        if pub is None:
            return False
        return (as_of - pub).days > max_age_days

    @property
    def effective_publication_date(self):
        return self.publication_date or self.source_date

    @property
    def planting_window_display(self) -> str:
        """How the dashboard should render planting dates. Never invents dates."""
        if self.planting_window_start is None or self.planting_window_end is None:
            return "Local planting dates not specified in this source"
        return f"{self.planting_window_start.isoformat()} to {self.planting_window_end.isoformat()}"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.crop} {self.get_season_display()} ({self.zone_label or self.zone})"
