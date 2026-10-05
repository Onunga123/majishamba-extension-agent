"""Custom user model for MajiShamba officers."""
from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """Named Nyatike extension officer (or supervisor / viewer)."""

    class Role(models.TextChoices):
        EXTENSION_OFFICER = "extension_officer", _("Extension Officer")
        SUPERVISOR = "supervisor", _("Supervisor")
        VIEWER = "viewer", _("Viewer")

    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.VIEWER,
        help_text=_("Determines whether the user can approve advisories."),
    )
    full_name = models.CharField(
        max_length=160,
        blank=True,
        help_text=_("Real-world officer name. Used in audit records."),
    )
    sub_county = models.CharField(
        max_length=80,
        default="Nyatike",
        help_text=_("Officer's assigned sub-county. Pinned to Nyatike for the demo."),
    )
    ward = models.CharField(
        max_length=80,
        default="Kachieng",
        help_text=_("Officer's assigned ward. Pinned to Kachieng for the demo."),
    )

    def is_officer(self) -> bool:
        return self.role in {self.Role.EXTENSION_OFFICER, self.Role.SUPERVISOR}

    def can_approve(self) -> bool:
        return self.role in {self.Role.EXTENSION_OFFICER, self.Role.SUPERVISOR}

    def display_name(self) -> str:
        return self.full_name or self.get_username()

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.display_name()} ({self.get_role_display()})"
