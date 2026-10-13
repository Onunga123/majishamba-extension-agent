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


def require_system_admin(user) -> None:
    if not (user and user.is_authenticated and user.can_review_accounts()):
        raise PermissionDenied("Only a System Administrator can manage account registrations.")
