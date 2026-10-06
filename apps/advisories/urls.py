"""URLs for the advisories app."""
from __future__ import annotations

from django.urls import path

from . import views

app_name = "advisories"

urlpatterns = [
    path("", views.AdvisoryListView.as_view(), name="list"),
    path("deleted/", views.DeletedAdvisoryListView.as_view(), name="deleted"),
    path("request/", views.RequestAdvisoryView.as_view(), name="request"),
    path("runs/<uuid:run_id>/", views.AdvisoryRunStatusView.as_view(), name="run_status"),
    path("runs/<uuid:run_id>/progress/", views.AdvisoryRunProgressPartialView.as_view(), name="run_progress"),
    path("<int:pk>/", views.AdvisoryDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.AdvisoryEditView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.AdvisorySoftDeleteView.as_view(), name="soft_delete"),
    path("<int:pk>/restore/", views.AdvisoryRestoreView.as_view(), name="restore"),
]
