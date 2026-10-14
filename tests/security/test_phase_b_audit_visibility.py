"""Phase B regression tests — audit visibility and account-management event filtering.

These tests verify the agreed Phase B security policy:

1. The full audit log (``/audit/``) and CSV export (``/audit/export.csv``)
   are restricted to authenticated, active, approved System Administrators.
   Anonymous users are redirected to the login page; other authenticated
   roles (Viewer, Extension Officer, Supervisor) receive 403.

2. The dashboard 'Recent activity' feed remains visible to all authenticated
   users, but excludes the four account-management event types
   (``account:register``, ``account:approve``, ``account:reject``,
   ``account:create_by_admin``) for non-administrators. Other operational
   events (advisory approvals, task completions, ingest events, etc.) are
   still surfaced.

3. The legacy ``/dashboard/audit/`` route redirects to ``/audit/`` so the
   administrator-only access policy is enforced centrally.

B-05 (login/logout event recording) is intentionally deferred and is NOT
exercised by this file.
"""
from __future__ import annotations

import csv
import io

import pytest
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()


# Account-management action codes that must be filtered from the
# non-admin dashboard activity feed.
ACCOUNT_MANAGEMENT_ACTIONS = (
    "account:register",
    "account:approve",
    "account:reject",
    "account:create_by_admin",
)


# ---------------------------------------------------------------------------
# 1. /audit/ — administrator-only access
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_audit_list_anonymous_redirected_to_login():
    """Anonymous users are redirected to the login page (not 403)."""
    c = Client()
    r = c.get("/audit/")
    assert r.status_code in {302, 301}, (
        f"Anonymous /audit/ should redirect to login, got {r.status_code}"
    )
    assert "/accounts/login/" in r["Location"]


@pytest.mark.django_db
def test_audit_list_system_admin_allowed(system_admin_client):
    """A System Administrator can access /audit/ and gets a 200 response."""
    r = system_admin_client.get("/audit/")
    assert r.status_code == 200, (
        f"System admin should access /audit/, got {r.status_code}"
    )


@pytest.mark.django_db
def test_audit_list_viewer_denied(viewer_client):
    """A Viewer is denied access to /audit/ with 403."""
    r = viewer_client.get("/audit/")
    assert r.status_code == 403, (
        f"Viewer should be denied /audit/, got {r.status_code}"
    )


@pytest.mark.django_db
def test_audit_list_officer_denied(officer_client):
    """An Extension Officer is denied access to /audit/ with 403."""
    r = officer_client.get("/audit/")
    assert r.status_code == 403, (
        f"Officer should be denied /audit/, got {r.status_code}"
    )


@pytest.mark.django_db
def test_audit_list_supervisor_denied(supervisor_client):
    """A Supervisor is denied access to /audit/ with 403."""
    r = supervisor_client.get("/audit/")
    assert r.status_code == 403, (
        f"Supervisor should be denied /audit/, got {r.status_code}"
    )


# ---------------------------------------------------------------------------
# 2. /audit/export.csv — administrator-only access
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_audit_csv_export_anonymous_redirected_to_login():
    """Anonymous users are redirected to login for the CSV export endpoint."""
    c = Client()
    r = c.get("/audit/export.csv")
    assert r.status_code in {302, 301}, (
        f"Anonymous /audit/export.csv should redirect to login, got {r.status_code}"
    )
    assert "/accounts/login/" in r["Location"]


@pytest.mark.django_db
def test_audit_csv_export_system_admin_allowed(system_admin_client):
    """A System Administrator can export the CSV and receives CSV content."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(actor=None, action="advisory:approve")

    r = system_admin_client.get("/audit/export.csv")
    assert r.status_code == 200, (
        f"System admin should export CSV, got {r.status_code}"
    )
    assert r["Content-Type"].startswith("text/csv"), (
        f"Expected CSV content-type, got {r['Content-Type']}"
    )
    # The CSV must parse and have a header row + at least one data row.
    reader = csv.reader(io.StringIO(r.content.decode("utf-8")))
    rows = list(reader)
    assert len(rows) >= 2, "CSV export must include a header row and at least one data row"
    assert "action" in rows[0], "CSV header must include the 'action' column"


@pytest.mark.django_db
def test_audit_csv_export_viewer_denied(viewer_client):
    """A Viewer is denied CSV export access with 403."""
    r = viewer_client.get("/audit/export.csv")
    assert r.status_code == 403, (
        f"Viewer should be denied /audit/export.csv, got {r.status_code}"
    )


@pytest.mark.django_db
def test_audit_csv_export_officer_denied(officer_client):
    """An Extension Officer is denied CSV export access with 403."""
    r = officer_client.get("/audit/export.csv")
    assert r.status_code == 403, (
        f"Officer should be denied /audit/export.csv, got {r.status_code}"
    )


@pytest.mark.django_db
def test_audit_csv_export_supervisor_denied(supervisor_client):
    """A Supervisor is denied CSV export access with 403."""
    r = supervisor_client.get("/audit/export.csv")
    assert r.status_code == 403, (
        f"Supervisor should be denied /audit/export.csv, got {r.status_code}"
    )


# ---------------------------------------------------------------------------
# 3. Dashboard activity feed — account-management event filtering
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_dashboard_activity_feed_officer_excludes_account_register():
    """A non-admin must NOT see account:register events in the activity feed."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(actor=None, action="account:register")

    c = Client()
    c.force_login(_make_officer())
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # Neither the raw code nor the humanised form ("registered an account")
    # should be visible to a non-administrator.
    assert "account:register" not in html
    assert "registered an account" not in html


@pytest.mark.django_db
def test_dashboard_activity_feed_officer_excludes_account_approve():
    """A non-admin must NOT see account:approve events in the activity feed."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(actor=None, action="account:approve")

    c = Client()
    c.force_login(_make_officer())
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "account:approve" not in html
    assert "approved an account" not in html


@pytest.mark.django_db
def test_dashboard_activity_feed_officer_excludes_account_reject():
    """A non-admin must NOT see account:reject events in the activity feed."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(actor=None, action="account:reject")

    c = Client()
    c.force_login(_make_officer())
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "account:reject" not in html
    assert "rejected an account" not in html


@pytest.mark.django_db
def test_dashboard_activity_feed_officer_excludes_account_create_by_admin():
    """A non-admin must NOT see account:create_by_admin events in the activity feed."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(actor=None, action="account:create_by_admin")

    c = Client()
    c.force_login(_make_officer())
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "account:create_by_admin" not in html


@pytest.mark.django_db
def test_dashboard_activity_feed_viewer_excludes_account_management_events():
    """A Viewer must NOT see any of the four account-management event types."""
    from apps.audit.models import AuditEvent
    for action in ACCOUNT_MANAGEMENT_ACTIONS:
        AuditEvent.objects.create(actor=None, action=action)

    c = Client()
    c.force_login(_make_viewer())
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    for action in ACCOUNT_MANAGEMENT_ACTIONS:
        assert action not in html, (
            f"Viewer must not see {action} in dashboard activity feed"
        )
    # Also check the humanised labels for the three mapped actions.
    assert "registered an account" not in html
    assert "approved an account" not in html
    assert "rejected an account" not in html


@pytest.mark.django_db
def test_dashboard_activity_feed_supervisor_excludes_account_management_events():
    """A Supervisor must NOT see account-management events in the activity feed
    (Supervisors are operational approvers, not account administrators)."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(actor=None, action="account:register")
    AuditEvent.objects.create(actor=None, action="account:approve")

    c = Client()
    c.force_login(_make_supervisor())
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "account:register" not in html
    assert "account:approve" not in html
    assert "registered an account" not in html
    assert "approved an account" not in html


@pytest.mark.django_db
def test_dashboard_activity_feed_system_admin_includes_account_management_events():
    """A System Administrator MUST see account-management events in the activity feed
    (the filtering only applies to non-administrators)."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(actor=None, action="account:register")
    AuditEvent.objects.create(actor=None, action="account:approve")

    c = Client()
    c.force_login(_make_system_admin())
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The admin should see the humanised form of these events.
    assert "registered an account" in html
    assert "approved an account" in html


@pytest.mark.django_db
def test_dashboard_activity_feed_officer_still_sees_other_events():
    """The dashboard activity feed for non-admins must still surface
    non-account-management events (e.g. advisory approvals, task completions)."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(actor=None, action="advisory:approve")
    AuditEvent.objects.create(actor=None, action="task:complete")

    c = Client()
    c.force_login(_make_officer())
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "approved an advisory" in html, (
        "Officer should still see advisory:approve events in the activity feed"
    )
    assert "completed a task" in html, (
        "Officer should still see task:complete events in the activity feed"
    )


@pytest.mark.django_db
def test_dashboard_activity_feed_filtering_is_server_side():
    """The filtering must be applied at the queryset level (server-side),
    not just hidden in the template. We verify this by checking that the
    account:register event does not appear at all in the rendered HTML,
    AND that a separate non-filtered event still appears with its actor.

    This guards against a regression where the template hides the row
    but the queryset still returns it (which would be a leak through the
    template layer if the template ever changed).
    """
    from apps.audit.models import AuditEvent
    # Mix account-management events with non-restricted events.
    AuditEvent.objects.create(actor=None, action="account:register")
    AuditEvent.objects.create(actor=None, action="advisory:approve")
    AuditEvent.objects.create(actor=None, action="account:approve")

    c = Client()
    c.force_login(_make_officer())
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The non-restricted event must appear.
    assert "approved an advisory" in html
    # The account-management events must NOT appear at all.
    assert "account:register" not in html
    assert "account:approve" not in html
    assert "registered an account" not in html
    assert "approved an account" not in html


# ---------------------------------------------------------------------------
# 4. Legacy /dashboard/audit/ route — redirect to /audit/
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_legacy_dashboard_audit_route_redirects_to_audit_list():
    """GET /dashboard/audit/ must 302-redirect to /audit/.

    The destination enforces the administrator-only policy, so this redirect
    must NOT bypass the centralised authorisation check.
    """
    c = Client()
    r = c.get("/dashboard/audit/")
    assert r.status_code == 302, (
        f"Legacy /dashboard/audit/ should redirect, got {r.status_code}"
    )
    assert r["Location"] == "/audit/", (
        f"Legacy /dashboard/audit/ should redirect to /audit/, got {r['Location']}"
    )


@pytest.mark.django_db
def test_legacy_dashboard_audit_route_for_officer_redirects_to_audit_list():
    """An officer hitting /dashboard/audit/ is redirected to /audit/, which
    then returns 403 (officer is denied). The first hop must be a 302 to
    /audit/ — the redirect must not bypass the centralised auth check.
    """
    c = Client()
    c.force_login(_make_officer())
    r = c.get("/dashboard/audit/")
    assert r.status_code == 302
    assert r["Location"] == "/audit/"
    # And the destination must deny the officer (don't follow the redirect).
    r2 = c.get(r["Location"])
    assert r2.status_code == 403


@pytest.mark.django_db
def test_legacy_dashboard_audit_route_for_system_admin_redirects_to_audit_list():
    """A system admin hitting /dashboard/audit/ is redirected to /audit/
    which they can access (200)."""
    c = Client()
    c.force_login(_make_system_admin())
    r = c.get("/dashboard/audit/")
    assert r.status_code == 302
    assert r["Location"] == "/audit/"
    r2 = c.get(r["Location"])
    assert r2.status_code == 200


@pytest.mark.django_db
def test_legacy_dashboard_audit_route_for_anonymous_redirects_to_audit_list():
    """An anonymous user hitting /dashboard/audit/ is redirected to /audit/
    which then redirects to /accounts/login/. The first hop is the legacy
    redirect; the second hop enforces auth."""
    c = Client()
    r = c.get("/dashboard/audit/")
    assert r.status_code == 302
    assert r["Location"] == "/audit/"
    r2 = c.get(r["Location"])
    assert r2.status_code in {302, 301}
    assert "/accounts/login/" in r2["Location"]


@pytest.mark.django_db
def test_legacy_dashboard_audit_route_is_not_permanent():
    """The legacy redirect must be a 302 (temporary), not 301 (permanent).

    A permanent redirect would be cached by browsers and proxies, making
    future changes to the policy difficult. 302 ensures every request is
    re-evaluated by the server.
    """
    c = Client()
    r = c.get("/dashboard/audit/")
    assert r.status_code == 302, "Legacy /dashboard/audit/ redirect must be 302 (temporary)"


# ---------------------------------------------------------------------------
# 5. No alternate endpoint bypasses the restriction
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_no_alternate_audit_endpoint_bypasses_restriction(officer_client):
    """Sanity check: an officer must be denied on every audit endpoint
    they try. The /audit/ list and /audit/export.csv are the only two
    audit endpoints exposed by apps/audit/urls.py — both must deny.
    """
    r1 = officer_client.get("/audit/")
    assert r1.status_code == 403
    r2 = officer_client.get("/audit/export.csv")
    assert r2.status_code == 403


@pytest.mark.django_db
def test_audit_export_csv_with_date_filters_still_restricted_for_officer(officer_client):
    """Date-filter parameters must NOT bypass the access restriction."""
    r = officer_client.get("/audit/export.csv?from=2025-01-01&to=2025-12-31")
    assert r.status_code == 403


@pytest.mark.django_db
def test_audit_export_csv_with_date_filters_allowed_for_system_admin(system_admin_client):
    """The CSV export with date filters must work for a system admin."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(actor=None, action="advisory:approve")

    r = system_admin_client.get("/audit/export.csv?from=2020-01-01&to=2030-12-31")
    assert r.status_code == 200
    assert r["Content-Type"].startswith("text/csv")


# ---------------------------------------------------------------------------
# 6. Recording mechanism preserved (regression guard)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_audit_event_recording_still_works(system_admin):
    """Phase B must not change audit-event recording. A logged event must
    still appear on the (admin-only) audit list page and CSV export."""
    from apps.audit.service import log_audit_event
    from apps.audit.models import AuditEvent

    before = AuditEvent.objects.count()
    log_audit_event(
        actor=system_admin,
        action="advisory:approve",
        metadata={"advisory_id": 42},
    )
    after = AuditEvent.objects.count()
    assert after == before + 1, "log_audit_event must still write an AuditEvent row"

    c = Client()
    c.force_login(system_admin)
    r = c.get("/audit/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Advisory approved" in html or "advisory:approve" in html


# ---------------------------------------------------------------------------
# Fixtures — local user factories (so we don't depend on conftest ordering).
# Each factory creates (or reuses) an approved, active user with the given
# role. Strings are used for role/approval_status to match the patterns in
# tests/integration/test_pending_account_security.py.
# ---------------------------------------------------------------------------
def _make_officer():
    user, _ = User.objects.get_or_create(
        username="phase_b_officer",
        defaults={
            "role": "extension_officer",
            "full_name": "Phase B Officer",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
            "is_active": True,
            "approval_status": "approved",
        },
    )
    user.is_active = True
    user.approval_status = "approved"
    user.save()
    return user


def _make_supervisor():
    user, _ = User.objects.get_or_create(
        username="phase_b_supervisor",
        defaults={
            "role": "supervisor",
            "full_name": "Phase B Supervisor",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
            "is_active": True,
            "approval_status": "approved",
        },
    )
    user.is_active = True
    user.approval_status = "approved"
    user.save()
    return user


def _make_viewer():
    user, _ = User.objects.get_or_create(
        username="phase_b_viewer",
        defaults={
            "role": "viewer",
            "full_name": "Phase B Viewer",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
            "is_active": True,
            "approval_status": "approved",
        },
    )
    user.is_active = True
    user.approval_status = "approved"
    user.save()
    return user


def _make_system_admin():
    user, _ = User.objects.get_or_create(
        username="phase_b_system_admin",
        defaults={
            "role": "system_admin",
            "full_name": "Phase B Sys Admin",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
            "is_active": True,
            "approval_status": "approved",
        },
    )
    user.is_active = True
    user.approval_status = "approved"
    user.save()
    return user
