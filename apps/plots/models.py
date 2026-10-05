"""Plot models — synthetic household plots and crop season records."""
from __future__ import annotations

from django.db import models

from apps.clusters.models import Household


class Plot(models.Model):
    """A synthetic household plot in Kachieng Ward."""

    class SoilType(models.TextChoices):
        SANDY = "sandy", "Sandy"
        LOAM = "loam", "Loam"
        CLAY = "clay", "Clay"
        SILT = "silt", "Silt-loam"
        UNKNOWN = "unknown", "Unknown"

    plot_id = models.CharField(max_length=30, unique=True)
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="plots")
    area_ha = models.FloatField(null=True, blank=True)
    centroid_lat = models.FloatField(null=True, blank=True)
    centroid_lon = models.FloatField(null=True, blank=True)
    soil_type = models.CharField(
        max_length=20,
        choices=SoilType.choices,
        default=SoilType.UNKNOWN,
    )
    irrigation = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.plot_id


class CropSeasonRecord(models.Model):
    """Planting history per plot per season — used by `get_cluster_plot_history`."""

    class Outcome(models.TextChoices):
        SUCCESS = "success", "Success"
        PARTIAL_FAILURE = "partial_failure", "Partial failure"
        TOTAL_FAILURE = "total_failure", "Total failure"
        DELAYED_PLANTING = "delayed_planting", "Delayed planting"
        UNKNOWN = "unknown", "Unknown"

    class YieldBand(models.TextChoices):
        LOW = "low", "Low (<1 t/ha)"
        MEDIUM = "medium", "Medium (1–3 t/ha)"
        HIGH = "high", "High (>3 t/ha)"
        UNKNOWN = "unknown", "Unknown"

    plot = models.ForeignKey(Plot, on_delete=models.CASCADE, related_name="season_records")
    season = models.CharField(max_length=40, help_text="e.g. '2024 short_rains'")
    crop = models.CharField(max_length=80, default="maize")
    planting_date = models.DateField(null=True, blank=True)
    harvest_date = models.DateField(null=True, blank=True)
    outcome = models.CharField(max_length=40, choices=Outcome.choices, default=Outcome.UNKNOWN)
    yield_band = models.CharField(max_length=40, choices=YieldBand.choices, default=YieldBand.UNKNOWN)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-season", "plot")
        unique_together = ("plot", "season", "crop")

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.plot.plot_id} {self.season} {self.crop}"
