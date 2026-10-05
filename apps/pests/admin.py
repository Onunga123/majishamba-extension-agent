from __future__ import annotations

from django.contrib import admin

from .models import PestAlert


@admin.register(PestAlert)
class PestAlertAdmin(admin.ModelAdmin):
    list_display = ("pest", "crop", "county", "region", "severity", "source", "source_date")
    list_filter = ("crop", "county", "severity")
    search_fields = ("pest", "advisory")
