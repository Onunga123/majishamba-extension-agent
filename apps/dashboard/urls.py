from __future__ import annotations

from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardHomeView.as_view(), name="home"),
    path("map/", views.ClusterMapView.as_view(), name="map"),
    path("audit/", views.AuditTrailView.as_view(), name="audit"),
]
