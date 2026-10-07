"""Custom user model for Kachieng AI Agent officers."""
from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """Named extension officer, supervisor, or viewer."""

    class Role(models.TextChoices):
        EXTENSION_OFFICER = "extension_officer", _("Extension Officer")
        SUPERVISOR = "supervisor", _("Supervisor")
        VIEWER = "viewer", _("Viewer")

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", _("Pending review")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        SUSPENDED = "suspended", _("Suspended")

    # --- Operational role (set by admin after approval) ---
    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.VIEWER,
        help_text=_("Effective operational role, set by an administrator after account approval."),
    )
    # --- Requested role (set by the user during registration) ---
    requested_role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.VIEWER,
        help_text=_("Role requested during registration. Does NOT grant privileges until approved."),
    )
    # --- Account lifecycle ---
    approval_status = models.CharField(
        max_length=32,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED,
        help_text=_("Account approval status. Pending users cannot access operational routes."),
    )
    approved_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="approved_accounts",
        help_text=_("Administrator who approved this account."),
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=300, blank=True)
    # --- Identity ---
    full_name = models.CharField(
        max_length=160,
        blank=True,
        help_text=_("Real-world officer name. Used in audit records."),
    )
    email = models.EmailField(blank=True, help_text=_("Officer email for notifications (if email is configured)."))
    sub_county = models.CharField(
        max_length=80,
        default="Nyatike",
        help_text=_("Officer's assigned sub-county."),
    )
    ward = models.CharField(
        max_length=80,
        default="Kachieng",
        help_text=_("Officer's assigned ward."),
    )
    organization = models.CharField(
        max_length=160,
        blank=True,
        help_text=_("Office/organization the officer belongs to (e.g. 'Nyatike Sub-County Agricultural Office')."),
    )

    def is_officer(self) -> bool:
        return self.role in {self.Role.EXTENSION_OFFICER, self.Role.SUPERVISOR}

    def can_approve(self) -> bool:
        return self.role in {self.Role.EXTENSION_OFFICER, self.Role.SUPERVISOR}

    def is_pending(self) -> bool:
        return self.approval_status == self.ApprovalStatus.PENDING

    def is_approved(self) -> bool:
        return self.approval_status == self.ApprovalStatus.APPROVED

    def is_suspended(self) -> bool:
        return self.approval_status == self.ApprovalStatus.SUSPENDED

    def display_name(self) -> str:
        return self.full_name or self.get_username()

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.display_name()} ({self.get_role_display()})"
