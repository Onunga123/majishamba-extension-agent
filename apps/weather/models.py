"""Weather signals — sourced from official publications (KMD) or officer field reports.

A WeatherSignal records a published forecast or observation for an area and period.
It is NEVER a "live station feed" — it is a snapshot of a specific bulletin issue.

Honest availability states (see docs/governance/source_access_register.md):
- current_official   — a current, applicable KMD bulletin
- regional_context   — a Lake Victoria Basin regional forecast that covers Migori
- officer_field_report — an authorized officer's verified local observation
- synthetic          — synthetic test scenario (clearly labelled)
- no_current_notice  — no current applicable notice found
"""
from __future__ import annotations

import datetime as dt

from django.db import models

from apps.geography.models import SubCounty
from apps.governance.provenance import ProvenanceMixin


class WeatherSignal(ProvenanceMixin):
    """A published forecast or observation for an area and period.

    ProvenanceMixin adds: source_authority, source_document_id, product_type,
    publication_date, observed_from/observed_to, valid_from/valid_to,
    geographic_scope, coverage_level, last_checked_at, raw_document_checksum,
    extraction_version, evidence_passage_reference, licence_or_permission_basis,
    permission_status, synthetic_flag, verification_status, extraction_review_status.
    """

    class Period(models.TextChoices):
        LAST_30_DAYS = "last_30_days", "Last 30 days"
        LAST_7_DAYS = "last_7_days", "Last 7 days"
        DAILY_FORECAST = "daily_forecast", "Daily forecast"
        FIVE_DAY_FORECAST = "5_day_forecast", "5-day forecast"
        SEVEN_DAY_FORECAST = "7_day_forecast", "7-day forecast"
        TEN_DAY_FORECAST = "10_day_forecast", "10-day forecast (legacy)"
        SEASONAL_OUTLOOK = "seasonal_outlook", "Seasonal outlook"

    sub_county = models.ForeignKey(
        SubCounty,
        on_delete=models.PROTECT,
        related_name="weather_signals",
        null=True,
        blank=True,
    )
    area_label = models.CharField(max_length=120, blank=True, help_text="Free-text area label if FK missing.")
    period = models.CharField(max_length=40, choices=Period.choices)
    # Numeric rainfall: stored ONLY when explicitly provided with units, period,
    # geographic scope, and observation/forecast distinction. NULL means "not provided",
    # NOT zero. The dashboard shows "Rainfall amount: Not specified in this bulletin" for NULL.
    rainfall_mm = models.FloatField(
        null=True, blank=True,
        help_text="Numeric rainfall in mm. Store ONLY when explicitly provided with units, period, scope, observation/forecast distinction. NULL means not provided.",
    )
    rainfall_units = models.CharField(max_length=20, blank=True, default="mm")
    rainfall_period_note = models.CharField(
        max_length=120, blank=True,
        help_text="Free-text note about the rainfall value's period/scope, e.g. 'Lake Victoria Basin, 24h forecast' or 'county 7-day total'.",
    )
    forecast_summary = models.TextField(blank=True, help_text="Qualitative forecast text as published, e.g. 'showers and thunderstorms'.")
    onset_status = models.CharField(
        max_length=80, blank=True, default="unknown",
        help_text="One of: 'onset_confirmed', 'onset_delayed', 'false_start', 'unknown'. Set to 'unknown' unless the authority explicitly reports onset OR an officer records a verified local observation. Do NOT infer onset from a 5/7-day forecast.",
    )
    confidence = models.CharField(
        max_length=20, default="medium",
        help_text="low / medium / high — qualitative confidence.",
    )
    # Legacy fields kept for backwards-compat with existing fixtures.
    source = models.CharField(max_length=160, blank=True, help_text="Legacy free-text source label; new records use source_authority + product_type.")
    source_url = models.URLField(blank=True)
    source_date = models.DateField(null=True, blank=True, help_text="Legacy alias for publication_date; new records use publication_date.")
    retrieved_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        ordering = ("-publication_date", "-source_date", "-retrieved_at")

    def is_fresh(self, *, as_of: dt.datetime | None = None, max_age_hours: int = 24) -> bool:
        if self.retrieved_at is None:
            return False
        if as_of is None:
            as_of = dt.datetime.now(tz=self.retrieved_at.tzinfo) if self.retrieved_at.tzinfo else dt.datetime.now()
        age_h = (as_of - self.retrieved_at).total_seconds() / 3600
        return age_h <= max_age_hours

    @property
    def effective_publication_date(self) -> dt.date | None:
        """The date the authority issued the document — publication_date if set, else source_date."""
        return self.publication_date or self.source_date

    @property
    def rainfall_display(self) -> str:
        """How the dashboard should render rainfall. Never 'None mm'."""
        if self.rainfall_mm is None:
            return "Not specified in this bulletin"
        return f"{self.rainfall_mm} {self.rainfall_units or 'mm'}"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.area_label or self.sub_county} {self.get_period_display()} {self.effective_publication_date}"
