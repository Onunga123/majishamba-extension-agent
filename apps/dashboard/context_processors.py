"""Context processors for nav-bar badges and global template context."""
from __future__ import annotations

from typing import Any


def nav_badges(request) -> dict[str, Any]:
    """Provide badge counts for the navigation bar (DRAFT advisories, pending tasks).

    Only computes for authenticated users; returns zeros for anonymous.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"nav_draft_advisory_count": 0, "nav_pending_task_count": 0}
    try:
        from apps.advisories.models import Advisory
        from apps.tasks.models import FollowUpTask
        draft = Advisory.objects.filter(status=Advisory.Status.DRAFT).count()
        pending = FollowUpTask.objects.exclude(status=FollowUpTask.Status.COMPLETED).count()
        return {"nav_draft_advisory_count": draft, "nav_pending_task_count": pending}
    except Exception:  # pragma: no cover — defensive: DB not ready at first migrate
        return {"nav_draft_advisory_count": 0, "nav_pending_task_count": 0}
