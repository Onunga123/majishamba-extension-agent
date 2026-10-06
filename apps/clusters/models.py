"""Farmer clusters for Kachieng Ward (KACH-01..KACH-14).

Geographic verification: locality names confirmed by the project owner
Onunga Christopher on 2026-10-06 (verification_status=locally_confirmed,
verification_method=project_owner_local_knowledge). Local confirmation of
a name does NOT establish coordinates or make the farmer groups real — all
household/plot/yield data remains explicitly synthetic.
"""
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
    # "locality" is the geographic type used for Kachieng clusters.
    # It is NOT an administrative village-unit/sub-location classification.
    # Local confirmation of a name does not establish its coordinates.
    locality = models.CharField(
        max_length=120, blank=True,
        help_text="Locality name (e.g. Sori, Kiranda). Confirmed by project owner; no government classification claimed.",
    )
    centroid_lat = models.FloatField(null=True, blank=True)
    centroid_lon = models.FloatField(null=True, blank=True)
    # Whether the lat/lon above are real verified coordinates or synthetic placeholders.
    coordinates_verified = models.BooleanField(
        default=False,
        help_text="True only if coordinates are verified real; False if synthetic or missing.",
    )
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
