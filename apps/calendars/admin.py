from __future__ import annotations

from django.contrib import admin

from .models import CropCalendar


@admin.register(CropCalendar)
class CropCalendarAdmin(admin.ModelAdmin):
    list_display = ("crop", "season", "zone_label", "planting_window_start", "planting_window_end", "source", "source_date")
    list_filter = ("crop", "season")
    search_fields = ("crop", "zone_label", "source")
