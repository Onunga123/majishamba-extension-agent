from __future__ import annotations

from django.contrib import admin

from .models import OfficerApproval


@admin.register(OfficerApproval)
class OfficerApprovalAdmin(admin.ModelAdmin):
    list_display = ("advisory", "officer", "decision", "created_at")
    list_filter = ("decision",)
