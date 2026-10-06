from __future__ import annotations

from django.contrib import admin

from .models import Advisory, AdvisoryEvidence


class AdvisoryEvidenceInline(admin.TabularInline):
    model = AdvisoryEvidence
    extra = 0


@admin.register(Advisory)
class AdvisoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "cluster",
        "recommendation_type",
        "status",
        "generation_mode",
        "ward",
        "sub_county",
        "county",
        "created_at",
    )
    list_filter = ("status", "recommendation_type", "generation_mode", "ward")
    search_fields = ("summary", "body")
    inlines = [AdvisoryEvidenceInline]


@admin.register(AdvisoryEvidence)
class AdvisoryEvidenceAdmin(admin.ModelAdmin):
    list_display = ("advisory", "source_type", "source_ref", "is_stale", "retrieved_at")
    list_filter = ("source_type", "is_stale")
