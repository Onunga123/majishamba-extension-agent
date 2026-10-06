"""Context processors exposed to all templates."""
from __future__ import annotations

from typing import Any

from django.http import HttpRequest


def active_officer(request: HttpRequest) -> dict[str, Any]:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {
            "active_officer": None,
            "user_can_request_advisory": False,
            "user_can_approve_advisory": False,
        }
    return {
        "active_officer": user,
        "user_can_request_advisory": user.is_officer(),
        "user_can_approve_advisory": user.can_approve(),
    }
