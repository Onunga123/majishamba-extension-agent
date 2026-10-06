"""Weather signals for Nyatike / Kachieng."""
from __future__ import annotations

import datetime as dt

from django.db import models

from apps.geography.models import SubCounty


class WeatherSignal(models.Model):
    """Rainfall / forecast observation for an area and period."""

    class Period(models.TextChoices):
        LAST_30_DAYS = "last_30_days", "Last 30 days"
        LAST_7_DAYS = "last_7_days", "Last 7 days"
        TEN_DAY_FORECAST = "10_day_forecast", "10-day forecast"
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
    rainfall_mm = models.FloatField(null=True, blank=True)
    forecast_summary = models.TextField(blank=True)
    onset_status = models.CharField(
        max_length=80,
        blank=True,
        help_text="One of: 'onset_confirmed', 'onset_delayed', 'false_start', 'unknown'.",
    )
    confidence = models.CharField(
        max_length=20,
        default="medium",
        help_text="low / medium / high — qualitative confidence.",
    )
    source = models.CharField(max_length=160)
    source_url = models.URLField(blank=True)
    source_date = models.DateField()
    retrieved_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        ordering = ("-source_date", "-retrieved_at")

    def is_fresh(self, *, as_of: dt.datetime | None = None, max_age_hours: int = 24) -> bool:
        if self.retrieved_at is None:
            return False
        if as_of is None:
            as_of = dt.datetime.now(tz=self.retrieved_at.tzinfo) if self.retrieved_at.tzinfo else dt.datetime.now()
        age_h = (as_of - self.retrieved_at).total_seconds() / 3600
        return age_h <= max_age_hours

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.area_label or self.sub_county} {self.get_period_display()} {self.source_date}"
