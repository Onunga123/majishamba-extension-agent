"""Middleware to capture request-level audit events."""
from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse

from .service import log_audit_event

logger = logging.getLogger("majishamba.audit")


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
