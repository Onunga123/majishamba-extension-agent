from __future__ import annotations

from django.urls import path

from . import views
from .health import HealthCheckView

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardHomeView.as_view(), name="home"),
    path("map/", views.ClusterMapView.as_view(), name="map"),
    path("audit/", views.AuditTrailView.as_view(), name="audit"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("guidance/", views.GuidanceView.as_view(), name="guidance"),
    path("data-sources/", views.DataSourcesView.as_view(), name="data_sources"),
    path("health/", HealthCheckView.as_view(), name="health"),
]
