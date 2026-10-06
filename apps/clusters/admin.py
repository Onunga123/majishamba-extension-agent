from __future__ import annotations

from django.contrib import admin

from .models import FarmerCluster, Household


@admin.register(FarmerCluster)
class FarmerClusterAdmin(admin.ModelAdmin):
    list_display = ("cluster_id", "name", "ward", "representative")
    list_filter = ("ward",)
    search_fields = ("cluster_id", "name", "representative")


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ("household_id", "cluster", "head_of_household")
    list_filter = ("cluster",)
    search_fields = ("household_id",)
