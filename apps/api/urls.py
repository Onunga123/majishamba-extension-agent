"""URL routes for the public API, mounted at ``/api/v1/``."""

from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("advisories/request/", views.request_advisory_view, name="request_advisory"),
    path("approvals/", views.record_approval_view, name="record_approval"),
    path("token/introspect/", views.token_introspect_view, name="token_introspect"),
    path("token/revoke/", views.token_revoke_view, name="token_revoke"),
]
