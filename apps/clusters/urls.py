from __future__ import annotations

from django.urls import path

from . import views

app_name = "clusters"

urlpatterns = [
    path("<str:cluster_id>/", views.ClusterDetailView.as_view(), name="detail"),
]
