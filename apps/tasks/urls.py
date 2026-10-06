from __future__ import annotations

from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("", views.FollowUpTaskListView.as_view(), name="list"),
]
