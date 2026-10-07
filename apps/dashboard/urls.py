from __future__ import annotations

from django.urls import path

from . import views
from .health import HealthCheckView

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardHomeView.as_view(), name="home"),
    path("map/", views.ClusterMapView.as_view(), name="map"),
    path("audit/", views.AuditTrailView.as_view(), name="audit"),
    path("health/", HealthCheckView.as_view(), name="health"),
]
