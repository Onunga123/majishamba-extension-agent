"""Geography models — counties, sub-counties, wards, agroclimatic zones."""
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
    # Generalised centroid (decimal degrees) — kept as plain floats so the demo
    # does not require PostGIS. Real deployments would use GeoDjango PointField.
    centroid_lat = models.FloatField(null=True, blank=True)
    centroid_lon = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ("sub_county", "name")

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name} ward, {self.sub_county.name}, {self.sub_county.county.name}"


class AgroClimaticZone(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    # Used to select the right crop calendar in this build
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
