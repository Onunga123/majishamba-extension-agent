"""Context processors exposed to all templates."""
from __future__ import annotations

from typing import Any

from django.http import HttpRequest


def active_officer(request: HttpRequest) -> dict[str, Any]:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"active_officer": None}
    return {"active_officer": user}
