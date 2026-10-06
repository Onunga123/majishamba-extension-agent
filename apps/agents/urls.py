from __future__ import annotations

from django.urls import path

from . import views

app_name = "agents"

urlpatterns = [
    path("graph/", views.AgentGraphView.as_view(), name="graph"),
]
