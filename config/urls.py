
"""Root URL configuration for MajiShamba Extension Agent."""
from __future__ import annotations

from django.contrib import admin
from django.conf import settings
from django.http import FileResponse
from django.views.decorators.http import require_GET
from django.templatetags.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from apps.dashboard.health import HealthCheckView

handler403 = "config.handlers.permission_denied"


@require_GET
def service_worker(request):
    worker_path = settings.BASE_DIR / "static" / "service-worker.js"
    response = FileResponse(
        worker_path.open("rb"),
        content_type="application/javascript",
    )
    response["Cache-Control"] = "no-cache"
    return response
urlpatterns = [
    path("service-worker.js", service_worker, name="service_worker"),
    path("admin/", admin.site.urls),

    # Serve the existing SVG logo when browsers request /favicon.ico.
    path(
        "favicon.ico",
        RedirectView.as_view(
            url=static("images/logo.svg"),
            permanent=True,
        ),
    ),

    path("accounts/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("dashboard/", include(("apps.dashboard.urls", "dashboard"), namespace="dashboard")),
    # F-10: narrow /health/ to a single health-check endpoint only.
    # Previously this mounted the entire dashboard app under /health/,
    # exposing /health/map/, /health/audit/, /health/about/, etc. as
    # duplicates of the dashboard routes. Those duplicates were also
    # exempt from AccountStatusMiddleware (which uses "/health/" as a
    # prefix), bypassing session-eligibility enforcement for those
    # shadow routes. The intended health endpoint is the JSON status
    # check at GET /health/ (documented in
    # docs/operations/readiness_register.md). The dashboard-internal
    # named route "dashboard:health" at /dashboard/health/ remains
    # available for any internal callers.
    path("health/", HealthCheckView.as_view(), name="health"),
    path("advisories/", include(("apps.advisories.urls", "advisories"), namespace="advisories")),
    path("clusters/", include(("apps.clusters.urls", "clusters"), namespace="clusters")),
    path("approvals/", include(("apps.approvals.urls", "approvals"), namespace="approvals")),
    path("tasks/", include(("apps.tasks.urls", "tasks"), namespace="tasks")),
    path("audit/", include(("apps.audit.urls", "audit"), namespace="audit")),
    path("mcp/", include(("apps.mcp_tools.urls", "mcp_tools"), namespace="mcp_tools")),
    path("agents/", include(("apps.agents.urls", "agents"), namespace="agents")),
    path("integrations/", include(("apps.integrations.urls", "integrations"), namespace="integrations")),
    path("geo/", include(("apps.geography.urls", "geography"), namespace="geography")),
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
]

# HTMX partials are served from each app's urls; no central router needed.
