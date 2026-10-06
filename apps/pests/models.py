"""Pest alert models — fall armyworm, storage pests in Migori/Nyanza."""
from __future__ import annotations

from django.db import models


class PestAlert(models.Model):
    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MODERATE = "moderate", "Moderate"
        HIGH = "high", "High"
        EXTREME = "extreme", "Extreme"

    crop = models.CharField(max_length=80, default="maize")
    pest = models.CharField(max_length=120)
    county = models.CharField(max_length=80, default="Migori")
    region = models.CharField(max_length=120, default="Nyanza")
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MODERATE)
    advisory = models.TextField()
    source = models.CharField(max_length=160)
    source_url = models.URLField(blank=True)
    source_date = models.DateField()
    retrieved_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        ordering = ("-source_date",)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.pest} ({self.get_severity_display()}) — {self.county} {self.source_date}"
