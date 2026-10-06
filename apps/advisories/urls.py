"""URLs for the advisories app."""
from __future__ import annotations

from django.urls import path

from . import views

app_name = "advisories"

urlpatterns = [
    path("", views.AdvisoryListView.as_view(), name="list"),
    path("<int:pk>/", views.AdvisoryDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.AdvisoryEditView.as_view(), name="edit"),
    path("request/", views.RequestAdvisoryView.as_view(), name="request"),
]
