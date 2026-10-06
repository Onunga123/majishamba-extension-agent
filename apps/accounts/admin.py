"""Admin registration for accounts."""
from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "full_name", "role", "sub_county", "ward", "is_staff")
    list_filter = ("role", "sub_county", "ward", "is_staff")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("MajiShamba officer", {"fields": ("role", "full_name", "sub_county", "ward")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("MajiShamba officer", {"fields": ("role", "full_name", "sub_county", "ward")}),
    )
