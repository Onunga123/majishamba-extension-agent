from __future__ import annotations

from django.contrib import admin

from .models import AgroClimaticZone, County, ExtensionOffice, SubCounty, Ward


@admin.register(County)
class CountyAdmin(admin.ModelAdmin):
    list_display = ("name", "code")


@admin.register(SubCounty)
class SubCountyAdmin(admin.ModelAdmin):
    list_display = ("name", "county", "code")
    list_filter = ("county",)


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ("name", "sub_county", "code", "centroid_lat", "centroid_lon")
    list_filter = ("sub_county",)


@admin.register(AgroClimaticZone)
class AgroClimaticZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "code")


@admin.register(ExtensionOffice)
class ExtensionOfficeAdmin(admin.ModelAdmin):
    list_display = ("name", "sub_county", "ward", "contact")
