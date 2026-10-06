from __future__ import annotations

from django.contrib import admin

from .models import FollowUpTask


@admin.register(FollowUpTask)
class FollowUpTaskAdmin(admin.ModelAdmin):
    list_display = ("id", "approved_advisory", "owner", "task_type", "deadline", "status", "ward")
    list_filter = ("task_type", "status", "ward")
