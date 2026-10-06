"""Permission helpers for officer-only actions."""
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


def require_officer(user) -> None:
    if not (user and user.is_authenticated and user.is_officer()):
        raise PermissionDenied("Only extension officers can perform this action.")


def require_approver(user) -> None:
    if not (user and user.is_authenticated and user.can_approve()):
        raise PermissionDenied("Only approvers (officers/supervisors) can perform this action.")
