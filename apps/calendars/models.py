"""Crop calendar models — Migori/Nyatike maize, short rains."""
from __future__ import annotations

import datetime as dt

from django.db import models

from apps.geography.models import AgroClimaticZone


class CropCalendar(models.Model):
    """Recommended activities and planting window for a crop in a zone/season."""

    class Season(models.TextChoices):
        SHORT_RAINS = "short_rains", "Short rains (Sep–Dec)"
        LONG_RAINS = "long_rains", "Long rains (Mar–Jul)"

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
    planting_window_start = models.DateField()
    planting_window_end = models.DateField()
    activities = models.JSONField(default=list, help_text="Ordered list of recommended activities.")
    source = models.CharField(max_length=160)
    source_url = models.URLField(blank=True)
    source_date = models.DateField()

    class Meta:
        ordering = ("-source_date",)
        unique_together = ("crop", "zone_label", "season")

    def is_stale(self, *, as_of: dt.date | None = None, max_age_days: int = 365 * 2) -> bool:
        as_of = as_of or dt.date.today()
        return (as_of - self.source_date).days > max_age_days

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.crop} {self.get_season_display()} ({self.zone_label or self.zone})"
