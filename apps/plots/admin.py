from __future__ import annotations

from django.contrib import admin

from .models import CropSeasonRecord, Plot


@admin.register(Plot)
class PlotAdmin(admin.ModelAdmin):
    list_display = ("plot_id", "household", "area_ha", "soil_type", "irrigation")
    list_filter = ("household__cluster", "soil_type")


@admin.register(CropSeasonRecord)
class CropSeasonRecordAdmin(admin.ModelAdmin):
    list_display = ("plot", "season", "crop", "planting_date", "outcome", "yield_band")
    list_filter = ("season", "crop", "outcome", "yield_band")
