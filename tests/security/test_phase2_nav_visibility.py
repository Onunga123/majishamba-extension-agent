"""Phase 2 regression tests — navigation visibility and 403 page wording.

Covers five Phase 2 remediation findings from the post-synchronization
audit:

  F-05: The "Agent graph" link in the user menu was gated on Django's
        ``is_staff`` flag. Officers provisioned via ``create_officer``
        have ``is_staff=False`` and could not discover the Agent graph
        page from the user menu. A Viewer with ``is_staff=True`` (mis-
        provisioned via the Django admin UI) would see the link but
        receive 403 on click. Phase 2 gates the link on
        ``user.is_officer or user.is_system_admin`` — consistent with
        the server-side check in ``AgentGraphView.test_func``.

  F-06: The "Audit" primary nav link was visible to all authenticated
        users. The /audit/ endpoint is restricted to System
        Administrators by ``require_system_admin()`` in
        ``AuditEventListView.get_queryset``. Phase 2 hides the link
        from Viewers, Officers, and Supervisors so they do not see a
        link they cannot follow.

  F-07: The dashboard "Audit log →" link (templates/dashboard/home.html)
        was visible to all authenticated users. Like F-06, Phase 2
        gates this link on ``is_system_admin`` so non-admins do not see
        an unusable link.

  F-08: The 403 page wording previously stated "Viewers can read
        dashboards, advisories, tasks and audit records only." — but
        Viewers cannot access /audit/ (Phase B requires System
        Administrator). Phase 2 removes the inaccurate "audit records"
        claim.

  F-04 is covered separately in tests/security/test_phase_b_audit_visibility.py
  (the technical-detail column visibility).

Out of scope: F-03 (dead AuditTrailView), F-09 (superuser task verify),
F-10 (/health/ route duplication), F-11 (unused templatetag), F-12
(missing semantic task audit events). These are deferred to Phase 3+.
"""
from __future__ import annotations

import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers — local user factories (match the patterns in conftest.py and
# tests/security/test_phase_b_audit_visibility.py).
# ---------------------------------------------------------------------------
def _make_user(username, role, full_name, *, is_staff=False):
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={
            "role": role,
            "full_name": full_name,
            "sub_county": "Nyatike",
            "ward": "Kachieng",
            "is_active": True,
            "approval_status": "approved",
            "is_staff": is_staff,
        },
    )
    user.is_active = True
    user.approval_status = "approved"
    user.is_staff = is_staff
    user.set_password("test-pw-123")
    user.save()
    return user


def _make_officer():
    return _make_user("phase2_officer", "extension_officer", "Phase2 Officer")


def _make_supervisor():
    return _make_user("phase2_supervisor", "supervisor", "Phase2 Supervisor")


def _make_viewer():
    return _make_user("phase2_viewer", "viewer", "Phase2 Viewer")


def _make_system_admin():
    # System Administrator provisioned via create_system_admin: is_staff=False
    return _make_user(
        "phase2_system_admin", "system_admin", "Phase2 Sys Admin", is_staff=False
    )


def _make_viewer_with_is_staff_true():
    """A Viewer mis-provisioned with is_staff=True via Django admin UI.
    F-05 must NOT show this user the Agent graph link (the server-side
    check denies access anyway; the nav must match).
    """
    return _make_user(
        "phase2_staff_viewer", "viewer", "Phase2 Staff Viewer", is_staff=True
    )


def _primary_nav_html(html: str) -> str:
    """Extract the primary-nav <nav aria-label="Primary">…</nav> block."""
    m = re.search(r'<nav[^>]*aria-label="Primary"[^>]*>(.*?)</nav>', html, re.S)
    return m.group(1) if m else ""


def _user_menu_html(html: str) -> str:
    """Extract the <details id="user-menu">…</details> block."""
    m = re.search(r'<details[^>]*id="user-menu"[^>]*>(.*?)</details>', html, re.S)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# F-05: Agent Graph link in user menu
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_agent_graph_link_visible_to_officer():
    """F-05 regression: an Extension Officer sees the Agent graph link in
    the user menu. The Officer is the intended audience of the Agent
    graph page (per AgentGraphView.test_func).
    """
    officer = _make_officer()
    c = Client(); c.force_login(officer)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    menu_html = _user_menu_html(html)
    assert "/agents/graph/" in menu_html, (
        "Officer must see the Agent graph link in the user menu"
    )
    assert "Agent graph" in menu_html


@pytest.mark.django_db
def test_agent_graph_link_visible_to_supervisor():
    """F-05 regression: a Supervisor sees the Agent graph link in the
    user menu (Supervisors are officers under is_officer()).
    """
    supervisor = _make_supervisor()
    c = Client(); c.force_login(supervisor)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    menu_html = _user_menu_html(html)
    assert "/agents/graph/" in menu_html


@pytest.mark.django_db
def test_agent_graph_link_visible_to_system_admin():
    """F-05 regression: a System Administrator sees the Agent graph link
    in the user menu.
    """
    admin = _make_system_admin()
    c = Client(); c.force_login(admin)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    menu_html = _user_menu_html(html)
    assert "/agents/graph/" in menu_html


@pytest.mark.django_db
def test_agent_graph_link_hidden_from_viewer():
    """F-05 regression: a Viewer does NOT see the Agent graph link in the
    user menu. The AgentGraphView denies Viewers via test_func, so the
    nav must not show a link the Viewer cannot follow.
    """
    viewer = _make_viewer()
    c = Client(); c.force_login(viewer)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    menu_html = _user_menu_html(html)
    assert "/agents/graph/" not in menu_html, (
        "Viewer must NOT see the Agent graph link in the user menu"
    )


@pytest.mark.django_db
def test_agent_graph_link_hidden_from_viewer_with_is_staff_true():
    """F-05 regression: a Viewer mis-provisioned with ``is_staff=True``
    must NOT see the Agent graph link. The link is gated on the
    application role (``is_officer or is_system_admin``), not on
    Django's ``is_staff`` flag.
    """
    staff_viewer = _make_viewer_with_is_staff_true()
    c = Client(); c.force_login(staff_viewer)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    menu_html = _user_menu_html(html)
    assert "/agents/graph/" not in menu_html, (
        "Viewer with is_staff=True must NOT see the Agent graph link "
        "(nav must match server-side authorization)"
    )


# ---------------------------------------------------------------------------
# F-05: Direct URL access authorisation (regression guard)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_agent_graph_view_officer_allowed():
    """F-05 regression: an Officer can access /agents/graph/ directly."""
    officer = _make_officer()
    c = Client(); c.force_login(officer)
    r = c.get("/agents/graph/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_agent_graph_view_supervisor_allowed():
    """F-05 regression: a Supervisor can access /agents/graph/ directly."""
    supervisor = _make_supervisor()
    c = Client(); c.force_login(supervisor)
    r = c.get("/agents/graph/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_agent_graph_view_system_admin_allowed():
    """F-05 regression: a System Administrator can access /agents/graph/."""
    admin = _make_system_admin()
    c = Client(); c.force_login(admin)
    r = c.get("/agents/graph/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_agent_graph_view_viewer_denied():
    """F-05 regression: a Viewer receives 403 from /agents/graph/."""
    viewer = _make_viewer()
    c = Client(); c.force_login(viewer)
    r = c.get("/agents/graph/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_agent_graph_view_viewer_with_is_staff_true_denied():
    """F-05 regression: a Viewer with is_staff=True is still denied
    (server-side check uses the role, not is_staff).
    """
    staff_viewer = _make_viewer_with_is_staff_true()
    c = Client(); c.force_login(staff_viewer)
    r = c.get("/agents/graph/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_agent_graph_view_anonymous_denied():
    """F-05 regression: anonymous users are denied (403, not 200).
    ``AgentGraphView`` uses ``UserPassesTestMixin`` with
    ``raise_exception=True``, which raises ``PermissionDenied`` (403)
    for any failing test_func — including anonymous users. (Other
    pages that use ``LoginRequiredMixin`` without ``raise_exception``
    redirect anonymous users to /accounts/login/; the AgentGraphView
    is intentionally strict because it is a technical reference page
    not intended for unauthenticated visitors.)
    """
    c = Client()
    r = c.get("/agents/graph/")
    assert r.status_code == 403, (
        f"Anonymous users must be denied /agents/graph/ — got {r.status_code}"
    )


# ---------------------------------------------------------------------------
# F-06: Audit primary nav link
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_audit_nav_link_visible_to_system_admin():
    """F-06 regression: a System Administrator sees the Audit nav link."""
    admin = _make_system_admin()
    c = Client(); c.force_login(admin)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    nav_html = _primary_nav_html(html)
    assert "/audit/" in nav_html, (
        "System Administrator must see the Audit nav link"
    )
    # "Audit" link text must appear in the primary nav
    link_texts = re.findall(r'<a[^>]*href="/audit/"[^>]*>\s*(\w+)', nav_html)
    assert any("Audit" in t for t in link_texts), (
        "Audit nav link must contain the text 'Audit'"
    )


@pytest.mark.django_db
def test_audit_nav_link_hidden_from_officer():
    """F-06 regression: an Officer does NOT see the Audit nav link (the
    /audit/ page is restricted to System Administrators).
    """
    officer = _make_officer()
    c = Client(); c.force_login(officer)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    nav_html = _primary_nav_html(html)
    assert "/audit/" not in nav_html, (
        "Officer must NOT see the Audit nav link "
        "(server-side /audit/ requires System Administrator)"
    )


@pytest.mark.django_db
def test_audit_nav_link_hidden_from_supervisor():
    """F-06 regression: a Supervisor does NOT see the Audit nav link."""
    supervisor = _make_supervisor()
    c = Client(); c.force_login(supervisor)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    nav_html = _primary_nav_html(html)
    assert "/audit/" not in nav_html


@pytest.mark.django_db
def test_audit_nav_link_hidden_from_viewer():
    """F-06 regression: a Viewer does NOT see the Audit nav link."""
    viewer = _make_viewer()
    c = Client(); c.force_login(viewer)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    nav_html = _primary_nav_html(html)
    assert "/audit/" not in nav_html


# ---------------------------------------------------------------------------
# F-06: Direct URL access authorisation (regression guard)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_audit_view_system_admin_allowed():
    """F-06 regression: a System Administrator can access /audit/."""
    admin = _make_system_admin()
    c = Client(); c.force_login(admin)
    r = c.get("/audit/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_audit_view_officer_denied():
    """F-06 regression: an Officer receives 403 from /audit/."""
    officer = _make_officer()
    c = Client(); c.force_login(officer)
    r = c.get("/audit/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_audit_view_supervisor_denied():
    """F-06 regression: a Supervisor receives 403 from /audit/."""
    supervisor = _make_supervisor()
    c = Client(); c.force_login(supervisor)
    r = c.get("/audit/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_audit_view_viewer_denied():
    """F-06 regression: a Viewer receives 403 from /audit/."""
    viewer = _make_viewer()
    c = Client(); c.force_login(viewer)
    r = c.get("/audit/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_audit_view_anonymous_redirected_to_login():
    """F-06 regression: anonymous users are redirected to login."""
    c = Client()
    r = c.get("/audit/")
    assert r.status_code in {302, 301}
    assert "/accounts/login/" in r["Location"]


# ---------------------------------------------------------------------------
# F-07: Dashboard "Audit log →" link in the Recent activity section
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_dashboard_audit_log_link_visible_to_system_admin():
    """F-07 regression: a System Administrator sees the "Audit log →" link
    on the dashboard home (Recent activity section heading).
    """
    admin = _make_system_admin()
    c = Client(); c.force_login(admin)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The "Audit log →" link text + URL must appear
    assert "/audit/" in html
    assert "Audit log" in html


@pytest.mark.django_db
def test_dashboard_audit_log_link_hidden_from_officer():
    """F-07 regression: an Officer does NOT see the "Audit log →" link
    on the dashboard home (the /audit/ page is restricted to System
    Administrators). The "Recent activity" heading still appears; only
    the link is hidden.
    """
    officer = _make_officer()
    c = Client(); c.force_login(officer)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The "Recent activity" section heading still appears
    assert "Recent activity" in html
    # The "Audit log →" link must NOT appear
    assert "Audit log" not in html, (
        "Officer must NOT see the 'Audit log →' link on the dashboard"
    )


@pytest.mark.django_db
def test_dashboard_audit_log_link_hidden_from_supervisor():
    """F-07 regression: a Supervisor does NOT see the "Audit log →" link."""
    supervisor = _make_supervisor()
    c = Client(); c.force_login(supervisor)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Audit log" not in html


@pytest.mark.django_db
def test_dashboard_audit_log_link_hidden_from_viewer():
    """F-07 regression: a Viewer does NOT see the "Audit log →" link."""
    viewer = _make_viewer()
    c = Client(); c.force_login(viewer)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Audit log" not in html


@pytest.mark.django_db
def test_dashboard_audit_log_link_direct_url_officer_denied():
    """F-07 regression: an Officer cannot bypass the dashboard link by
    directly requesting /audit/ (server-side check still enforces).
    """
    officer = _make_officer()
    c = Client(); c.force_login(officer)
    r = c.get("/audit/")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# F-08: 403 page wording accuracy
# ---------------------------------------------------------------------------
def _trigger_403_for(role_user):
    """Trigger a 403 response for the given role by requesting /audit/.
    Returns the rendered 403.html HTML.
    """
    c = Client(); c.force_login(role_user)
    r = c.get("/audit/")
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    return r.content.decode("utf-8")


@pytest.mark.django_db
def test_403_page_does_not_claim_viewer_can_access_audit_records():
    """F-08 regression: the 403 page must NOT state that Viewers can
    access audit records. Viewers are denied at /audit/ (Phase B requires
    System Administrator). The previously-inaccurate wording "Viewers
    can read dashboards, advisories, tasks and audit records only" must
    NOT appear.
    """
    viewer = _make_viewer()
    html = _trigger_403_for(viewer)
    # The inaccurate statement must NOT appear
    assert "audit records" not in html.lower(), (
        "403 page must NOT claim Viewers can access audit records — "
        "Phase B restricts /audit/ to System Administrators"
    )
    # Specifically the previously-rendered wording must be gone
    assert "Viewers can read dashboards, advisories, tasks and audit records only" not in html


@pytest.mark.django_db
def test_403_page_describes_viewer_permissions_accurately():
    """F-08 regression: the 403 page must accurately describe Viewer
    permissions — dashboards, advisories and tasks (NOT audit records).
    """
    viewer = _make_viewer()
    html = _trigger_403_for(viewer)
    # The accurate wording must appear
    assert "dashboards" in html.lower()
    assert "advisories" in html.lower()
    assert "tasks" in html.lower()


@pytest.mark.django_db
def test_403_page_officer_still_describes_officer_permissions():
    """F-08 regression: the 403 page still accurately describes Officer
    and Supervisor permissions ("request and review advisories").
    The change must NOT remove or alter unrelated wording.
    """
    officer = _make_officer()
    html = _trigger_403_for(officer)
    assert "Extension officers and supervisors can request and review advisories" in html


@pytest.mark.django_db
def test_403_page_viewer_does_not_impersonate_other_role_text():
    """F-08 regression: a Viewer who triggers a 403 sees Viewer-specific
    wording, not Officer wording. The page does NOT mislead the Viewer
    into thinking they have officer privileges.
    """
    viewer = _make_viewer()
    html = _trigger_403_for(viewer)
    # The Viewer's role display appears
    assert viewer.get_role_display() in html
    # The Viewer-permission line is the corrected wording (with
    # "dashboards, advisories and tasks only")
    assert "dashboards, advisories and tasks only" in html.lower()


# ---------------------------------------------------------------------------
# Phase 1 F-01/F-02 privacy protections remain intact (regression guard)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_phase1_dashboard_activity_feed_viewer_redaction_still_intact():
    """Phase 1 F-01 regression: a Viewer still does NOT see officer
    usernames in the dashboard activity feed. Phase 2 must not weaken
    this protection.
    """
    from apps.audit.models import AuditEvent
    officer = _make_officer()
    viewer = _make_viewer()
    AuditEvent.objects.create(actor=officer, action="advisory:approve")
    c = Client(); c.force_login(viewer)
    r = c.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert officer.username not in html
    assert officer.username.title() not in html
    assert officer.full_name not in html


@pytest.mark.django_db
def test_phase1_advisory_detail_approval_history_redaction_still_intact():
    """Phase 1 F-02 regression: a Viewer still does NOT see officer
    names in the advisory approval history. Phase 2 must not weaken
    this protection.
    """
    from apps.advisories.models import Advisory
    from apps.approvals.models import OfficerApproval
    from tests.factories.models import AdvisoryFactory
    officer = _make_officer()
    viewer = _make_viewer()
    adv = AdvisoryFactory(status=Advisory.Status.APPROVED)
    OfficerApproval.objects.create(advisory=adv, officer=officer, decision="approved")
    c = Client(); c.force_login(viewer)
    r = c.get(f"/advisories/{adv.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert officer.full_name not in html
    assert officer.username not in html
    assert "Officer" in html  # role label still rendered


# ---------------------------------------------------------------------------
# F-13: Audit-trail link visibility on advisory detail, approval gate, and
#       dashboard about page (Phase 6 remediation)
#
# Phase 6 gates the three remaining ungated audit-log links on
# ``user.is_system_admin``, matching the Phase 2 F-06/F-07 policy.
# Before Phase 6, these three links were visible to non-admin users,
# leading to a 403 response at /audit/.
#
# Link locations:
#   1. templates/advisories/detail.html — "Audit trail" link in the
#      approval-history aside. Reachable by all authenticated users
#      (AdvisoryDetailView uses LoginRequiredMixin only).
#   2. templates/approvals/gate.html — "Audit trail" link in the
#      approval-history aside. Reachable only by Officers and Supervisors
#      (require_approver → can_approve → is_officer). A System
#      Administrator CANNOT reach this page (403) because
#      is_system_admin does not imply is_officer.
#   3. templates/dashboard/about.html — "Full audit log" link in the
#      "More" section. Reachable by all authenticated users.
#
# For the approval gate (location 2), the link can only be seen by
# Officers and Supervisors — and after the F-13 fix, neither should see
# it because neither is a System Administrator. There is no role that
# can both reach the approval gate AND see the audit-trail link.
# ---------------------------------------------------------------------------
def _make_advisory_with_approval_for_f13(officer, decision="approved", advisory_status="approved"):
    """Create an APPROVED Advisory with an OfficerApproval by ``officer``,
    for the F-13 advisory-detail and approval-gate tests.
    """
    from tests.factories.models import AdvisoryFactory
    from apps.approvals.models import OfficerApproval

    adv = AdvisoryFactory(status=advisory_status)
    OfficerApproval.objects.create(advisory=adv, officer=officer, decision=decision)
    return adv


def _make_draft_advisory_for_gate():
    """Create a DRAFT Advisory for the approval gate test (the gate
    requires the advisory to be in DRAFT status).
    """
    from tests.factories.models import AdvisoryFactory

    return AdvisoryFactory(status="draft")


# ---------------------------------------------------------------------------
# F-13 (1): Advisory detail — "Audit trail" link in approval-history aside
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_advisory_detail_audit_trail_link_visible_to_system_admin():
    """F-13 regression: a System Administrator sees the "Audit trail"
    link on the advisory detail page (approval-history aside).
    """
    from apps.advisories.models import Advisory

    officer = _make_officer()
    admin = _make_system_admin()
    adv = _make_advisory_with_approval_for_f13(officer, advisory_status="approved")

    c = Client(); c.force_login(admin)
    r = c.get(f"/advisories/{adv.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The "Audit trail" link text + the audit URL must appear
    assert "Audit trail" in html
    assert "/audit/" in html


@pytest.mark.django_db
def test_advisory_detail_audit_trail_link_hidden_from_viewer():
    """F-13 regression: a Viewer does NOT see the "Audit trail" link on
    the advisory detail page. The approval-history aside still renders
    (with role labels per F-02); only the audit-trail link is hidden.
    """
    officer = _make_officer()
    viewer = _make_viewer()
    adv = _make_advisory_with_approval_for_f13(officer, advisory_status="approved")

    c = Client(); c.force_login(viewer)
    r = c.get(f"/advisories/{adv.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The "Approval history" section heading still appears (Phase 1 F-02)
    assert "Approval history" in html
    # The "Audit trail" link text must NOT appear
    assert "Audit trail" not in html, (
        "Viewer must NOT see the 'Audit trail' link on the advisory detail page"
    )
    # The audit URL must not appear in an href attribute in the approval-history
    # aside. We check the full HTML — the /audit/ URL should not be present
    # because the only link to /audit/ on this page is the gated "Audit trail" link.
    # (Other links to /audit/ do not appear on the advisory detail page.)
    assert 'href="/audit/"' not in html, (
        "Viewer must NOT see the /audit/ href on the advisory detail page"
    )


@pytest.mark.django_db
def test_advisory_detail_audit_trail_link_hidden_from_officer():
    """F-13 regression: an Extension Officer does NOT see the "Audit
    trail" link on the advisory detail page.
    """
    officer = _make_officer()
    adv = _make_advisory_with_approval_for_f13(officer, advisory_status="approved")

    c = Client(); c.force_login(officer)
    r = c.get(f"/advisories/{adv.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Audit trail" not in html, (
        "Officer must NOT see the 'Audit trail' link on the advisory detail page"
    )
    assert 'href="/audit/"' not in html


@pytest.mark.django_db
def test_advisory_detail_audit_trail_link_hidden_from_supervisor():
    """F-13 regression: a Supervisor does NOT see the "Audit trail" link
    on the advisory detail page. (Supervisor is an officer but NOT a
    System Administrator.)
    """
    officer = _make_officer()
    supervisor = _make_supervisor()
    adv = _make_advisory_with_approval_for_f13(officer, advisory_status="approved")

    c = Client(); c.force_login(supervisor)
    r = c.get(f"/advisories/{adv.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Audit trail" not in html
    assert 'href="/audit/"' not in html


# ---------------------------------------------------------------------------
# F-13 (2): Approval gate — "Audit trail" link in approval-history aside
#
# Access constraint: the approval gate (/approvals/<pk>/) requires
# require_approver → can_approve → is_officer. Only Extension Officers
# and Supervisors can reach the page. A System Administrator CANNOT
# reach the page (is_system_admin does not imply is_officer → 403).
#
# Therefore: after the F-13 fix, no role sees the "Audit trail" link on
# the approval gate. Officers and Supervisors reach the page but are
# not System Admins (link hidden). System Admins cannot reach the page
# (403). The tests below verify:
#   - Officers do NOT see the link (negative).
#   - Supervisors do NOT see the link (negative).
#   - System Admins receive 403 (access constraint documented, not a
#     test of the link itself).
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_approval_gate_audit_trail_link_hidden_from_officer():
    """F-13 regression: an Extension Officer does NOT see the "Audit
    trail" link on the approval gate page. The approval gate is
    reachable by Officers (require_approver passes), but the audit-
    trail link is gated on is_system_admin.
    """
    officer = _make_officer()
    adv = _make_draft_advisory_for_gate()

    c = Client(); c.force_login(officer)
    r = c.get(f"/approvals/{adv.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The approval-gate page still renders (the "Approval history" or
    # "Governance record" section heading appears)
    assert "Governance record" in html or "Approval history" in html or "No decisions recorded yet" in html
    # The "Audit trail" link text must NOT appear
    assert "Audit trail" not in html, (
        "Officer must NOT see the 'Audit trail' link on the approval gate page"
    )
    assert 'href="/audit/"' not in html


@pytest.mark.django_db
def test_approval_gate_audit_trail_link_hidden_from_supervisor():
    """F-13 regression: a Supervisor does NOT see the "Audit trail" link
    on the approval gate page. Supervisors can reach the page (they are
    officers under is_officer()), but they are not System Administrators.
    """
    supervisor = _make_supervisor()
    adv = _make_draft_advisory_for_gate()

    c = Client(); c.force_login(supervisor)
    r = c.get(f"/approvals/{adv.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Audit trail" not in html, (
        "Supervisor must NOT see the 'Audit trail' link on the approval gate page"
    )
    assert 'href="/audit/"' not in html


@pytest.mark.django_db
def test_approval_gate_system_admin_denied_access():
    """F-13 access constraint: a System Administrator CANNOT reach the
    approval gate page because is_system_admin does not imply
    is_officer (require_approver → can_approve → is_officer returns
    False for SYSTEM_ADMIN). The System Admin receives 403, so the
    "Audit trail" link is never rendered to a System Admin on this
    page.

    This test documents the access constraint — the link cannot be
    shown to a System Admin via this page because the page itself is
    not accessible to System Admins. This is the existing application
    behavior and is NOT changed by Phase 6.
    """
    admin = _make_system_admin()
    adv = _make_draft_advisory_for_gate()

    c = Client(); c.force_login(admin)
    r = c.get(f"/approvals/{adv.id}/")
    assert r.status_code == 403, (
        f"System Admin should be denied access to the approval gate, got {r.status_code}"
    )


# ---------------------------------------------------------------------------
# F-13 (3): Dashboard About page — "Full audit log" link in "More" section
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_about_page_full_audit_log_link_visible_to_system_admin():
    """F-13 regression: a System Administrator sees the "Full audit log"
    link on the dashboard about page (More section).
    """
    admin = _make_system_admin()
    c = Client(); c.force_login(admin)
    r = c.get("/dashboard/about/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Full audit log" in html
    assert 'href="/audit/"' in html


@pytest.mark.django_db
def test_about_page_full_audit_log_link_hidden_from_viewer():
    """F-13 regression: a Viewer does NOT see the "Full audit log" link
    on the dashboard about page. The "More" section heading and other
    links still appear; only the audit-log link is hidden.
    """
    viewer = _make_viewer()
    c = Client(); c.force_login(viewer)
    r = c.get("/dashboard/about/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The "More" section heading still appears
    assert "More" in html
    # The other links in the "More" section still appear
    assert "Agronomic guidance" in html
    assert "Data sources" in html
    assert "Back to dashboard" in html
    # The "Full audit log" link text must NOT appear
    assert "Full audit log" not in html, (
        "Viewer must NOT see the 'Full audit log' link on the about page"
    )
    assert 'href="/audit/"' not in html


@pytest.mark.django_db
def test_about_page_full_audit_log_link_hidden_from_officer():
    """F-13 regression: an Extension Officer does NOT see the "Full
    audit log" link on the dashboard about page.
    """
    officer = _make_officer()
    c = Client(); c.force_login(officer)
    r = c.get("/dashboard/about/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Full audit log" not in html
    assert 'href="/audit/"' not in html


@pytest.mark.django_db
def test_about_page_full_audit_log_link_hidden_from_supervisor():
    """F-13 regression: a Supervisor does NOT see the "Full audit log"
    link on the dashboard about page. (Supervisor is an officer but
    NOT a System Administrator.)
    """
    supervisor = _make_supervisor()
    c = Client(); c.force_login(supervisor)
    r = c.get("/dashboard/about/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Full audit log" not in html
    assert 'href="/audit/"' not in html
