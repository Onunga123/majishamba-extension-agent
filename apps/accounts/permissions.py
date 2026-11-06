"""Permission helpers for distinct operational and account-admin actions."""
from __future__ import annotations

from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class OfficerRequiredMixin(UserPassesTestMixin):
    """Only extension officers / supervisors can pass."""

    raise_exception = True

    def test_func(self) -> bool:  # type: ignore[override]
        user = self.request.user
        return bool(user.is_authenticated and user.is_officer())


class ApproverRequiredMixin(UserPassesTestMixin):
    raise_exception = True

    def test_func(self) -> bool:  # type: ignore[override]
        user = self.request.user
        return bool(user.is_authenticated and user.can_approve())


class SystemAdminRequiredMixin(UserPassesTestMixin):
    """Only an approved System Administrator may manage user accounts."""

    raise_exception = True

    def test_func(self) -> bool:  # type: ignore[override]
        user = self.request.user
        return bool(user.is_authenticated and user.can_review_accounts())


def require_officer(user) -> None:
    if not (user and user.is_authenticated and user.is_officer()):
        raise PermissionDenied("Only extension officers can perform this action.")


def require_approver(user) -> None:
    if not (user and user.is_authenticated and user.can_approve()):
        raise PermissionDenied("Only approvers (officers/supervisors) can perform this action.")


def require_advisory_requester(user) -> None:
    """An extension officer (or supervisor) or a system admin may request advisory runs.

    Broader than ``require_officer`` so an admin token (bound to a system admin)
    can drive the full advisory flow from the Base44 role switcher. Web views
    that must stay officer-only still use ``require_officer`` directly.
    """
    if not (
        user
        and user.is_authenticated
        and (user.is_officer() or user.is_system_admin())
    ):
        raise PermissionDenied("Only extension officers or admins can request advisory runs.")


def require_approver_or_admin(user) -> None:
    """An approver (officer/supervisor) or a system admin may record approvals."""
    if not (
        user
        and user.is_authenticated
        and (user.can_approve() or user.is_system_admin())
    ):
        raise PermissionDenied("Only approvers or admins can record approvals.")


def require_system_admin(user) -> None:
    if not (user and user.is_authenticated and user.can_review_accounts()):
        raise PermissionDenied("Only a System Administrator can manage account registrations.")
