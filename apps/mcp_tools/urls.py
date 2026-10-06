from __future__ import annotations

from django.urls import path

from . import views

app_name = "mcp_tools"

urlpatterns = [
    path("tools/", views.MCPToolListView.as_view(), name="tool_list"),
    path("tools/<str:tool_name>/call/", views.MCPToolCallView.as_view(), name="tool_call"),
]
