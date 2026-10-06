"""Template helpers mirroring server-side permission checks."""
from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def can_request_advisory(user) -> bool:
    return bool(user and user.is_authenticated and user.is_officer())


@register.filter
def can_approve_advisory(user) -> bool:
    return bool(user and user.is_authenticated and user.can_approve())
