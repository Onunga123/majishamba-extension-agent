"""URLs for the geography app."""
from __future__ import annotations

from django.urls import path

from . import views

app_name = "geography"

urlpatterns = [
    path("localities.json", views.LocalityListJSONView.as_view(), name="localities_json"),
]
