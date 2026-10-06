"""Geography models — counties, sub-counties, wards, agroclimatic zones,
locality coordinates."""
from __future__ import annotations

from django.db import models


class County(models.Model):
    name = models.CharField(max_length=80, unique=True)
    code = models.CharField(max_length=20, blank=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


class SubCounty(models.Model):
    county = models.ForeignKey(County, on_delete=models.CASCADE, related_name="sub_counties")
    name = models.CharField(max_length=80)
    code = models.CharField(max_length=20, blank=True)

    class Meta:
        unique_together = ("county", "name")

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name}, {self.county.name}"


class Ward(models.Model):
    sub_county = models.ForeignKey(SubCounty, on_delete=models.CASCADE, related_name="wards")
    name = models.CharField(max_length=80)
    code = models.CharField(max_length=20, blank=True)
    centroid_lat = models.FloatField(null=True, blank=True)
    centroid_lon = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ("sub_county", "name")

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name} ward, {self.sub_county.name}, {self.sub_county.county.name}"


class AgroClimaticZone(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    code = models.CharField(max_length=40, blank=True, unique=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


class ExtensionOffice(models.Model):
    """The Nyatike Sub-County Agricultural Office."""

    name = models.CharField(max_length=160)
    sub_county = models.ForeignKey(SubCounty, on_delete=models.PROTECT, related_name="offices")
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="offices", null=True, blank=True)
    contact = models.CharField(max_length=120, blank=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


class LocalityCoordinate(models.Model):
    """Geographic reference point for a Kachieng locality.

    Keeps locality geography SEPARATE from synthetic farmer-group membership.
    A locality marker represents a geographic reference point — NOT the location
    of synthetic households or farm plots.

    Coordinate types:
    - settlement_reference: OSM settlement/village feature
    - landmark_reference: school, church, market, beach, etc.
    - official_centroid: official ward/county centroid
    - owner_confirmed_reference: approved by the project owner / officer
    - synthetic: synthetic placeholder (never displayed as real)

    Verification status:
    - candidate: geocoded but not yet reviewed/approved
    - approved: reviewed and confirmed
    - rejected: reviewed and rejected (coordinates not displayed)
    """

    class CoordinateType(models.TextChoices):
        SETTLEMENT_REFERENCE = "settlement_reference", "Settlement reference"
        LANDMARK_REFERENCE = "landmark_reference", "Landmark reference"
        OFFICIAL_CENTROID = "official_centroid", "Official centroid"
        OWNER_CONFIRMED = "owner_confirmed_reference", "Owner confirmed reference"
        SYNTHETIC = "synthetic", "Synthetic"

    class VerificationStatus(models.TextChoices):
        CANDIDATE = "candidate", "Candidate (awaiting review)"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    cluster = models.OneToOneField(
        "clusters.FarmerCluster",
        on_delete=models.CASCADE,
        related_name="locality_coordinate",
    )
    locality_name = models.CharField(max_length=120)
    latitude = models.FloatField()
    longitude = models.FloatField()
    coordinate_source = models.CharField(max_length=120, help_text="e.g. 'OpenStreetMap Nominatim'")
    source_feature_id = models.CharField(max_length=120, blank=True, help_text="OSM feature id")
    source_url = models.URLField(blank=True, help_text="Link to the OSM feature")
    retrieved_at = models.DateTimeField(auto_now=True)
    coordinate_type = models.CharField(
        max_length=40, choices=CoordinateType.choices, default=CoordinateType.SETTLEMENT_REFERENCE,
    )
    verification_status = models.CharField(
        max_length=40, choices=VerificationStatus.choices, default=VerificationStatus.CANDIDATE,
    )
    verified_by = models.CharField(max_length=160, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("cluster__cluster_id",)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.cluster.cluster_id} — {self.locality_name} ({self.coordinate_type})"
