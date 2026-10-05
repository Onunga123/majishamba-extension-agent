from __future__ import annotations

from django.contrib import admin

from .models import WeatherSignal


@admin.register(WeatherSignal)
class WeatherSignalAdmin(admin.ModelAdmin):
    list_display = ("area_label", "sub_county", "period", "rainfall_mm", "onset_status", "source", "source_date")
    list_filter = ("period", "onset_status")
