"""Market price signals — Migori Town, nearby markets."""
from __future__ import annotations

from django.db import models


class MarketPriceSignal(models.Model):
    crop = models.CharField(max_length=80, default="maize")
    market = models.CharField(max_length=120, default="Migori-Town")
    price_kes_per_90kg = models.FloatField()
    observation_date = models.DateField()
    trend = models.CharField(
        max_length=40,
        blank=True,
        help_text="One of: 'rising', 'falling', 'stable', 'unknown'.",
    )
    source = models.CharField(max_length=160)
    source_url = models.URLField(blank=True)
    retrieved_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        ordering = ("-observation_date",)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.crop} @ {self.market} KES {self.price_kes_per_90kg}/90kg ({self.observation_date})"
