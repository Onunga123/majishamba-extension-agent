"""Test factories — light, factory_boy-powered."""
from __future__ import annotations

import factory
from django.contrib.auth import get_user_model

from apps.accounts.models import User
from apps.advisories.models import Advisory, AdvisoryEvidence
from apps.clusters.models import FarmerCluster, Household
from apps.geography.models import County, ExtensionOffice, SubCounty, Ward
from apps.plots.models import CropSeasonRecord, Plot


class CountyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = County
        django_get_or_create = ("name",)

    name = "Migori"
    code = "MG-20"


class SubCountyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubCounty
        django_get_or_create = ("county", "name")

    county = factory.SubFactory(CountyFactory)
    name = "Nyatike"
    code = "NYA-01"


class WardFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Ward
        django_get_or_create = ("sub_county", "name")

    sub_county = factory.SubFactory(SubCountyFactory)
    name = "Kachieng"
    code = "KACH"
    centroid_lat = -0.965
    centroid_lon = 34.445


class OfficeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExtensionOffice

    name = "Nyatike Sub-County Agricultural Office"
    sub_county = factory.SubFactory(SubCountyFactory)
    ward = factory.SubFactory(WardFactory)


class FarmerClusterFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FarmerCluster
        django_get_or_create = ("cluster_id",)

    cluster_id = "KACH-01"
    name = "Kachieng North Cluster"
    ward = factory.SubFactory(WardFactory)
    office = factory.SubFactory(OfficeFactory)
    centroid_lat = -0.952
    centroid_lon = 34.432


class HouseholdFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Household
        django_get_or_create = ("household_id",)

    household_id = "KACH-01-HH-001"
    cluster = factory.SubFactory(FarmerClusterFactory)


class PlotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Plot
        django_get_or_create = ("plot_id",)

    plot_id = "KACH-01-HH-001-P1"
    household = factory.SubFactory(HouseholdFactory)
    area_ha = 0.6


class CropSeasonRecordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CropSeasonRecord

    plot = factory.SubFactory(PlotFactory)
    season = "2024 short_rains"
    crop = "maize"
    outcome = CropSeasonRecord.Outcome.SUCCESS
    yield_band = CropSeasonRecord.YieldBand.MEDIUM


class OfficerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = "officer_factory"
    role = User.Role.EXTENSION_OFFICER
    full_name = "Factory Officer"
    sub_county = "Nyatike"
    ward = "Kachieng"


class AdvisoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Advisory

    cluster = factory.SubFactory(FarmerClusterFactory)
    recommendation_type = Advisory.Recommendation.PLANT
    status = Advisory.Status.DRAFT
    summary = "Planting window suitable (factory)."
    body = "Body text long enough to be substantive for schema validation. " * 4
    confidence = "medium"
    generation_mode = "fallback_template"


class AdvisoryEvidenceFactory(factory.django.DjangoModelFactory):
    """Factory for AdvisoryEvidence rows used in evidence-quality tests."""
    class Meta:
        model = AdvisoryEvidence

    advisory = factory.SubFactory(AdvisoryFactory)
    source_type = "weather"
    source_ref = "WeatherSignal#test"
    claim = "Test evidence claim — supports the advisory's recommendation."
    is_stale = False
