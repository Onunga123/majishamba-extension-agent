from __future__ import annotations

from django.urls import path

from . import views

app_name = "approvals"

urlpatterns = [
    path("<int:advisory_pk>/", views.ApprovalGateView.as_view(), name="gate"),
]
