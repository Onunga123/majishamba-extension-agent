"""Context processors for nav-bar badges and global template context."""
from __future__ import annotations

from typing import Any
from django.conf import settings


def nav_badges(request) -> dict[str, Any]:
    """Provide badge counts for the navigation bar.

    The Advisories badge shows the TOTAL advisory count (all statuses,
    excluding soft-deleted), matching the count on the Advisories page
    heading. The 'drafts awaiting review' attention indicator lives in
    the 'Needs your attention' section on the dashboard, not in the nav.

    The Tasks badge shows the count of non-completed follow-up tasks.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"nav_advisory_count": 0, "nav_pending_task_count": 0, "DEMO_MODE": False}
    try:
        from apps.advisories.models import Advisory
        from apps.tasks.models import FollowUpTask
        # Total advisory count (default manager excludes soft-deleted)
        advisory_total = Advisory.objects.count()
        pending = FollowUpTask.objects.exclude(status=FollowUpTask.Status.COMPLETED).count()
        demo_mode = bool(settings.MAJISHAMBA.get("DEMO_MODE", False)) and bool(settings.DEBUG)
        return {"nav_advisory_count": advisory_total, "nav_pending_task_count": pending, "DEMO_MODE": demo_mode}
    except Exception:  # pragma: no cover — defensive: DB not ready at first migrate
        return {"nav_advisory_count": 0, "nav_pending_task_count": 0, "DEMO_MODE": False}
