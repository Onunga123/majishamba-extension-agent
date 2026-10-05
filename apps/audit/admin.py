from __future__ import annotations

from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "tool_name", "target_type", "target_id", "approval_status")
    list_filter = ("action", "tool_name", "approval_status")
    search_fields = ("action", "tool_name", "metadata")
    readonly_fields = ("created_at",)
