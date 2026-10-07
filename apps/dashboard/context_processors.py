"""Context processors for nav-bar badges and global template context."""
from __future__ import annotations

from typing import Any
from django.conf import settings


def nav_badges(request) -> dict[str, Any]:
    """Provide badge counts for the navigation bar (DRAFT advisories, pending tasks).

    Only computes for authenticated users; returns zeros for anonymous.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"nav_draft_advisory_count": 0, "nav_pending_task_count": 0, "DEMO_MODE": False}
    try:
        from apps.advisories.models import Advisory
        from apps.tasks.models import FollowUpTask
        draft = Advisory.objects.filter(status=Advisory.Status.DRAFT).count()
        pending = FollowUpTask.objects.exclude(status=FollowUpTask.Status.COMPLETED).count()
        demo_mode = bool(settings.MAJISHAMBA.get("DEMO_MODE", False)) and bool(settings.DEBUG)
        return {"nav_draft_advisory_count": draft, "nav_pending_task_count": pending, "DEMO_MODE": demo_mode}
    except Exception:  # pragma: no cover — defensive: DB not ready at first migrate
        return {"nav_draft_advisory_count": 0, "nav_pending_task_count": 0, "DEMO_MODE": False}
