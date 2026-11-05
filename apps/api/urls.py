"""URL routes for the public API, mounted at ``/api/v1/``."""

from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    # Endpoint 3 — request an advisory run (roadmap canonical path).
    path("advisories/", views.request_advisory_view, name="request_advisory"),
    # Back-compat alias for earlier clients; same view, same handler.
    path("advisories/request/", views.request_advisory_view, name="request_advisory_legacy"),
    # Endpoint 5 — advisory draft + evidence.
    path("advisories/<int:advisory_pk>/", views.advisory_detail_view, name="advisory_detail"),
    # Endpoint 4 — run-status polling.
    path("runs/<uuid:run_id>/", views.run_status_view, name="run_status"),
    path("approvals/", views.record_approval_view, name="record_approval"),
    path("token/introspect/", views.token_introspect_view, name="token_introspect"),
    path("token/revoke/", views.token_revoke_view, name="token_revoke"),
]
