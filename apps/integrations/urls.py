"""URLs for the integrations app — officer-supplied data ingestion."""
from __future__ import annotations

from django.urls import path

from . import views

app_name = "integrations"

urlpatterns = [
    path("", views.IntegrationsIndexView.as_view(), name="index"),
    path("kmd/ingest/", views.KMDBulletinIngestView.as_view(), name="kmd_ingest"),
    path("pests/report/", views.OfficerFieldReportView.as_view(), name="pest_report"),
    path("pests/notice/", views.PublishedPestNoticeView.as_view(), name="pest_notice"),
]
