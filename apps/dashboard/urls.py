from __future__ import annotations

from django.urls import path
from django.views.generic import RedirectView

from . import views
from .health import HealthCheckView

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardHomeView.as_view(), name="home"),
    path("map/", views.ClusterMapView.as_view(), name="map"),
    # Legacy audit route — Phase B: redirect to the admin-only /audit/ view.
    # /audit/ enforces the SystemAdministrator-only access policy; this
    # redirect keeps backward-compatible URLs working without bypassing
    # the centralised authorisation check.
    path("audit/", RedirectView.as_view(url="/audit/", permanent=False), name="audit"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("guidance/", views.GuidanceView.as_view(), name="guidance"),
    path("data-sources/", views.DataSourcesView.as_view(), name="data_sources"),
    path("health/", HealthCheckView.as_view(), name="health"),
]
