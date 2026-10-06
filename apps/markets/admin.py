from __future__ import annotations

from django.contrib import admin

from .models import MarketPriceSignal


@admin.register(MarketPriceSignal)
class MarketPriceSignalAdmin(admin.ModelAdmin):
    list_display = ("crop", "market", "price_kes_per_90kg", "trend", "observation_date", "source")
    list_filter = ("crop", "market", "trend")
