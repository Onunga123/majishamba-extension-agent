"""Middleware to capture request-level audit events.

Logs HTTP-level audit events for POST/PUT/PATCH/DELETE on sensitive paths.
Excludes paths where the view already logs a semantic event (e.g. the
advisory restore/delete views log 'advisory:restore'/'advisory:soft_delete'
and the task complete/verify/findings views log their own events). Without
this exclusion, those actions would produce two audit entries for one
logical operation — one semantic and one HTTP-level — which appears as
duplicate entries in the Recent activity feed.
"""
from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse

from .service import log_audit_event

logger = logging.getLogger("majishamba.audit")

# Paths where the view already logs a semantic audit event. The middleware
# skips these to avoid duplicate entries for a single logical action.
_EXCLUDED_SUFFIXES = (
    "/restore/",
    "/delete/",
    "/soft_delete/",
    "/complete/",
    "/verify/",
    "/findings/",
)


class AuditMiddleware:
    def __init__(self, get_response) -> None:  # type: ignore[no-untyped-def]
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Only audit POST/PUT/DELETE on sensitive paths
        method = request.method
        path = request.path
        if method in {"POST", "PUT", "PATCH", "DELETE"} and any(
            p in path for p in ("/advisories/", "/approvals/", "/tasks/", "/agents/", "/mcp/")
        ):
            # Skip paths where the view already logs a semantic event.
            # This prevents duplicate audit entries for a single logical action
            # (e.g. restoring an advisory logs both 'advisory:restore' from
            # the view AND 'http:POST:/advisories/12/restore/' from the
            # middleware — we only want the semantic one).
            if not any(path.endswith(suffix) for suffix in _EXCLUDED_SUFFIXES):
                log_audit_event(
                    actor=getattr(request, "user", None),
                    action=f"http:{method}:{path}",
                    inputs_summary={
                        "method": method,
                        "path": path,
                        "post_keys": list(request.POST.keys()) if method == "POST" else [],
                    },
                    outputs_summary=None,
                )
        return self.get_response(request)
