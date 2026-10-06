"""Root URL configuration for MajiShamba Extension Agent."""
from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

handler403 = "config.handlers.permission_denied"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("dashboard/", include(("apps.dashboard.urls", "dashboard"), namespace="dashboard")),
    path("advisories/", include(("apps.advisories.urls", "advisories"), namespace="advisories")),
    path("clusters/", include(("apps.clusters.urls", "clusters"), namespace="clusters")),
    path("approvals/", include(("apps.approvals.urls", "approvals"), namespace="approvals")),
    path("tasks/", include(("apps.tasks.urls", "tasks"), namespace="tasks")),
    path("audit/", include(("apps.audit.urls", "audit"), namespace="audit")),
    path("mcp/", include(("apps.mcp_tools.urls", "mcp_tools"), namespace="mcp_tools")),
    path("agents/", include(("apps.agents.urls", "agents"), namespace="agents")),
    path("integrations/", include(("apps.integrations.urls", "integrations"), namespace="integrations")),
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
]

# HTMX partials are served from each app's urls; no central router needed.
