"""Farmer clusters for Kachieng Ward (KACH-01, KACH-02, KACH-03)."""
from __future__ import annotations

from django.db import models

from apps.geography.models import ExtensionOffice, Ward


class FarmerCluster(models.Model):
    cluster_id = models.CharField(
        max_length=20,
        unique=True,
        help_text="Human-readable cluster code e.g. 'KACH-01'.",
    )
    name = models.CharField(max_length=160)
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="clusters")
    office = models.ForeignKey(
        ExtensionOffice,
        on_delete=models.PROTECT,
        related_name="clusters",
        null=True,
        blank=True,
    )
    representative = models.CharField(max_length=160, blank=True, help_text="Synthetic representative name.")
    contact = models.CharField(max_length=120, blank=True)
    centroid_lat = models.FloatField(null=True, blank=True)
    centroid_lon = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.cluster_id} — {self.name}"


class Household(models.Model):
    """Pseudonymous household linked to a Kachieng cluster. SYNTHETIC."""

    household_id = models.CharField(max_length=30, unique=True)
    cluster = models.ForeignKey(FarmerCluster, on_delete=models.CASCADE, related_name="households")
    head_of_household = models.CharField(
        max_length=160,
        blank=True,
        help_text="Pseudonymous identifier. No real names used in synthetic fixtures.",
    )
    phone_e164 = models.CharField(max_length=20, blank=True, help_text="Synthetic phone for demo only.")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("household_id",)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.household_id
