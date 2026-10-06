from __future__ import annotations

from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("", views.FollowUpTaskListView.as_view(), name="list"),
    path("<int:pk>/", views.FollowUpTaskDetailView.as_view(), name="detail"),
    path("<int:pk>/findings/", views.TaskFieldFindingView.as_view(), name="findings"),
    path("<int:pk>/complete/", views.TaskCompleteView.as_view(), name="complete"),
    path("<int:pk>/verify/", views.TaskVerifyView.as_view(), name="verify"),
]
