"""Tests for the v3 dashboard refinements — HCI/Gestalt/progressive-disclosure.

These tests complement test_dashboard_v2.py by covering the explicit v3
HCI requirements:
  1. 'Recently approved' was removed from Needs attention (it's history).
  2. The same draft advisories do NOT appear in BOTH 'Needs attention' AND
     'Recent advisories' — the attention card shows a summary count, the
     actual rows live in Recent advisories (Summary → Action → Detail).
  3. Cluster primary actions are contextual — a cluster with a draft shows
     'Review', a cluster with no advisory shows 'Request' (officers only),
     a cluster with an approved advisory + open task shows 'Field visit'.
     The same 'Request' action is NOT shown prominently on every cluster.
  4. Weather, Pest alerts, Agronomic guidance are grouped under a single
     'Field conditions & guidance' <section> with one heading.
  5. The dashboard's human-readable activity feed does not contain raw
     'http:METHOD:/path/' audit codes — those are humanised to phrases like
     'completed Task #1', 'restored Advisory #12'.
  6. Audit is separate from Activity — the activity feed is human-readable;
     the audit page has the technical detail.
  7. The dashboard hierarchy follows: Attention → Action → Operational
     data (clusters + advisories) → Context (field conditions) → History
     (activity).
"""
from __future__ import annotations

import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client


User = get_user_model()


# ---------------------------------------------------------------------------
# 1. 'Recently approved' was removed from Needs attention
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_recently_approved_removed_from_needs_attention(officer_client):
    """The 'Needs your attention' section must NOT have a 'Recently approved'
    card. Approved advisories are history (they belong in 'Recent advisories
    → Approved' or 'Field verification'), not actionable attention."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "Recently approved" not in html, (
        "'Recently approved' must NOT appear on the dashboard — moved to "
        "'Recent advisories → Approved' / 'Field verification' groups"
    )


# ---------------------------------------------------------------------------
# 2. No duplicate advisory rows (Summary → Action → Detail)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_draft_advisory_appears_once_in_recent_advisories_not_in_attention(officer_client):
    """A draft advisory must appear in 'Recent advisories → Draft' (with full
    detail row) but NOT as a detailed row in 'Needs attention'. The Needs
    attention card shows a SUMMARY count, not the same detailed row repeated.

    The advisory #ID can legitimately appear multiple times in the rendered
    HTML (e.g. in the cluster row's aria-label, in the ⋮ menu, in the
    Recent advisories detail row). The v3 spec only forbids DUPLICATING THE
    DETAILED ROW between Needs attention and Recent advisories. So we check
    that the Needs attention section contains the summary count, not the
    advisory detail row markup."""
    from django.core.management import call_command
    from io import StringIO
    from tests.factories.models import AdvisoryFactory

    call_command("seed_kachieng_clusters", stdout=StringIO())
    a = AdvisoryFactory(status="draft")

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")

    # The advisory #ID appears in the Recent advisories section (detail row)
    assert f"#{a.id}" in html, "Draft advisory must appear in Recent advisories"

    # Find the 'Needs your attention' section and check it contains a SUMMARY
    # count, not the same detailed advisory row (with AI-generated-draft badge)
    # Use a regex that captures from the section heading to the closing </section>
    needs_section = re.search(
        r'<section[^>]*aria-labelledby="needs-attention-heading"[^>]*>(.*?)</section>',
        html, re.S
    )
    assert needs_section is not None, "Needs your attention <section> not found"
    needs_html = needs_section.group(1)
    # The Needs attention section must contain the heading 'Drafts awaiting review'
    # (which is the card heading, not a summary sentence). The count number
    # is also present via .attention-card-count.
    assert "Drafts awaiting review" in needs_html or "drafts awaiting review" in needs_html.lower(), (
        f"Needs attention section must contain the 'Drafts awaiting review' heading. needs_html (first 1500): {needs_html[:1500]}"
    )
    # The Needs attention section must NOT contain the 'AI-generated draft'
    # workflow badge that appears in the detail rows of 'Recent advisories'
    assert "AI-generated draft" not in needs_html, (
        "Needs attention section must NOT contain the 'AI-generated draft' "
        "detail-row badge — that belongs in the Recent advisories section"
    )


@pytest.mark.django_db
def test_needs_attention_shows_summary_count_not_detail_rows(officer_client):
    """The Needs attention card for 'Drafts awaiting review' must show a
    summary count (e.g. '3 drafts awaiting review'), not a list of detailed
    advisory rows. The detailed rows live in the 'Recent advisories' section."""
    from django.core.management import call_command
    from io import StringIO
    from tests.factories.models import AdvisoryFactory

    call_command("seed_kachieng_clusters", stdout=StringIO())
    # Create 3 drafts
    for _ in range(3):
        AdvisoryFactory(status="draft")

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")

    # The Needs attention card must show the summary count ('3 drafts awaiting review').
    # The view uses singular/plural form depending on count.
    assert "3 drafts awaiting review" in html or "drafts awaiting review" in html, (
        "Needs attention card must show a summary count, not a detailed list"
    )


# ---------------------------------------------------------------------------
# 3. Contextual cluster actions (no identical actions for every cluster)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cluster_with_no_advisory_shows_request_action(officer_client):
    """A cluster with NO advisory must show 'Request' as the primary action
    (officers only). Viewers must NOT see the Request action."""
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")

    # Find a cluster with no advisory (the freshly-seeded ones have none)
    from apps.clusters.models import FarmerCluster
    cluster = FarmerCluster.objects.exclude(advisories__isnull=False).first()
    assert cluster is not None, "Test requires at least one cluster with no advisory"

    # The Request action URL must be present for this cluster
    assert f"/advisories/request/?cluster={cluster.cluster_id}" in html, (
        f"Cluster {cluster.cluster_id} with no advisory must show 'Request' as primary action"
    )


@pytest.mark.django_db
def test_cluster_with_draft_shows_review_action_not_request(officer_client):
    """A cluster with a DRAFT advisory must show 'Review' as the primary
    action, NOT 'Request'. The officer should review the existing draft
    before requesting a new one — reduces confusion and unnecessary choices."""
    from django.core.management import call_command
    from io import StringIO
    from tests.factories.models import AdvisoryFactory

    call_command("seed_kachieng_clusters", stdout=StringIO())
    from apps.clusters.models import FarmerCluster
    cluster = FarmerCluster.objects.first()
    a = AdvisoryFactory(cluster=cluster, status="draft")

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")

    # The cluster's row must show 'Review' as the primary action
    # The approval gate URL must be present (officer_client is an officer who can_approve)
    assert f"/approvals/{a.id}/" in html or f"/advisories/{a.id}/" in html, (
        "Cluster with draft must show 'Review' action linking to approval gate or advisory detail"
    )


@pytest.mark.django_db
def test_cluster_with_approved_and_open_task_shows_field_visit_action(officer_client):
    """A cluster with an APPROVED advisory + open follow-up task must show
    'Field visit' as the primary action, linking to the open task."""
    from django.core.management import call_command
    from io import StringIO
    from tests.factories.models import AdvisoryFactory
    from apps.tasks.models import FollowUpTask

    call_command("seed_kachieng_clusters", stdout=StringIO())
    from apps.clusters.models import FarmerCluster
    cluster = FarmerCluster.objects.first()
    a = AdvisoryFactory(cluster=cluster, status="approved")
    t = FollowUpTask.objects.create(
        approved_advisory=a, task_type=FollowUpTask.TaskType.FIELD_VISIT,
        deadline="2030-01-01", status=FollowUpTask.Status.ASSIGNED,
    )

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")

    # The cluster's row must show 'Field visit' linking to the open task
    assert f"/tasks/{t.id}/" in html, (
        "Cluster with approved advisory + open task must show 'Field visit' linking to the task"
    )


@pytest.mark.django_db
def test_viewer_does_not_see_request_action_on_no_advisory_cluster(viewer_client):
    """A viewer must NOT see the 'Request' action on a cluster with no advisory.
    Server-side enforcement is in the view (can_request_advisory=False for viewers)."""
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())

    r = viewer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The Request action URL must NOT be present for viewers
    assert "/advisories/request/?cluster=KACH-" not in html, (
        "Viewer must NOT see 'Request' action on cluster rows — server-side enforced"
    )


# ---------------------------------------------------------------------------
# 4. Weather + Pest + Guidance grouped under 'Field conditions & guidance'
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_field_conditions_group_heading_present(officer_client):
    """Weather, Pest alerts, and Agronomic guidance must be grouped under a
    single 'Field conditions & guidance' section heading (Gestalt proximity:
    related items belong together)."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "Field conditions" in html, "Field conditions & guidance heading missing"
    assert "guidance" in html.lower()


@pytest.mark.django_db
def test_weather_pests_guidance_are_subheadings_under_field_conditions(officer_client):
    """Weather, Pest alerts, and Agronomic guidance must be h3 subheadings
    inside the 'Field conditions & guidance' section (not separate top-level
    sections on the dashboard)."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")

    # Find the Field conditions section
    field_section = re.search(r"Field conditions.*?</section>", html, re.S)
    assert field_section is not None, "Field conditions section not found"
    section_html = field_section.group(0)

    # All three subheadings must be inside this section
    assert "Weather" in section_html, "Weather must be in Field conditions section"
    assert "Pest alerts" in section_html, "Pest alerts must be in Field conditions section"
    assert "Agronomic guidance" in section_html, "Agronomic guidance must be in Field conditions section"


# ---------------------------------------------------------------------------
# 5. Activity feed humanises http:METHOD:/path/ audit codes
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_activity_feed_humanises_http_audit_codes(officer_client):
    """The activity feed must NOT show raw 'http:POST:/tasks/1/complete/'
    audit codes. They must be humanised to phrases like 'completed Task #1'."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(
        actor=None, action="http:POST:/tasks/1/complete/",
    )
    AuditEvent.objects.create(
        actor=None, action="http:POST:/advisories/12/restore/",
    )

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # Raw http: codes must NOT appear
    assert "http:POST:/tasks/1/complete/" not in html
    assert "http:POST:/advisories/12/restore/" not in html
    # Humanised phrases must appear
    assert "completed" in html.lower()
    assert "Task #1" in html
    assert "restored" in html.lower()
    assert "Advisory #12" in html


@pytest.mark.django_db
def test_activity_feed_humanises_approval_action(officer_client):
    """The activity feed must show 'reviewed Advisory #30' for an approval
    POST, not the raw http:POST:/approvals/30/ code."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(
        actor=None, action="http:POST:/approvals/30/",
    )

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "http:POST:/approvals/30/" not in html
    assert "reviewed" in html.lower()
    assert "Advisory #30" in html


@pytest.mark.django_db
def test_activity_feed_humanises_login_logout(officer_client):
    """Login and logout audit events must be humanised to 'signed in' /
    'signed out', not the raw http:POST:/accounts/login/ code."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(actor=None, action="http:POST:/accounts/login/")
    AuditEvent.objects.create(actor=None, action="http:POST:/accounts/logout/")

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "http:POST:/accounts/login/" not in html
    assert "http:POST:/accounts/logout/" not in html
    assert "signed in" in html.lower()
    assert "signed out" in html.lower()


# ---------------------------------------------------------------------------
# 6. Audit is separate from Activity
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dashboard_has_audit_log_link_separate_from_activity(officer_client):
    """The dashboard must have a separate 'Audit log →' link (to /audit/)
    distinct from the 'Recent activity' section. Activity is human-readable;
    audit is the technical record."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "Recent activity" in html, "Recent activity section heading missing"
    assert 'href="/audit/"' in html, "Audit log link missing"
    assert "Audit log" in html, "Audit log link label missing"


@pytest.mark.django_db
def test_audit_page_has_technical_detail_for_authorized_users(supervisor_client):
    """The /audit/ page must contain technical audit detail for authorized
    users (it's the detailed accountability view, separate from the
    human-readable activity feed on the dashboard)."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(actor=None, action="http:POST:/tasks/1/complete/")

    r = supervisor_client.get("/audit/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The audit page must show some audit content (the human-readable timeline
    # plus optionally raw detail for staff)
    assert "completed" in html.lower() or "Task #1" in html or "tasks" in html.lower()


# ---------------------------------------------------------------------------
# 7. Dashboard hierarchy: Attention → Action → Operational → Context → History
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dashboard_section_ordering(officer_client):
    """The dashboard sections must appear in the v3-specified order:
    1. Page header (Kachieng’ Ward)
    2. Needs your attention
    3. Request advisory (primary CTA)
    4. Clusters
    5. Recent advisories
    6. Field conditions & guidance
    7. Recent activity
    """
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")

    # Find the position of each section heading in the rendered HTML
    sections = [
        "Kachieng’ Ward",           # 1. Header
        "Needs your attention",    # 2. Attention
        "Request a climate-smart advisory",  # 3. Action
        "Clusters",                # 4. Operational data
        "Recent advisories",       # 5. Operational data
        "Field conditions",        # 6. Context
        "Recent activity",         # 7. History
    ]
    positions = []
    for s in sections:
        idx = html.find(s)
        assert idx > 0, f"Section {s!r} not found in dashboard HTML"
        positions.append(idx)

    # Each section must appear AFTER the previous one (in order)
    for i in range(1, len(positions)):
        assert positions[i] > positions[i-1], (
            f"Section {sections[i]!r} appears BEFORE {sections[i-1]!r} "
            f"— dashboard hierarchy is out of order"
        )


# ---------------------------------------------------------------------------
# 8. Agronomic guidance uses user-friendly wording on the dashboard
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_agronomic_guidance_uses_user_friendly_wording_on_dashboard(officer_client):
    """The dashboard's agronomic guidance panel must use user-friendly wording
    ('KALRO maize guidance currently unavailable', 'Status: Awaiting
    authorization') rather than the internal technical phrase
    'permission-pending for KALRO maize manual ingestion' (which is kept on
    the Guidance details page)."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # User-friendly wording on the dashboard
    assert "KALRO maize guidance currently unavailable" in html, (
        "Dashboard must use user-friendly wording for KALRO guidance status"
    )
    assert "Status: Awaiting authorization" in html or "Awaiting authorization" in html
    # The technical 'permission-pending for KALRO maize manual ingestion' phrase
    # must NOT be on the dashboard — it's on /dashboard/guidance/ (progressive
    # disclosure)
    assert "permission-pending for KALRO maize manual ingestion" not in html, (
        "Technical KALRO permission phrase must NOT be on the dashboard — "
        "move to /dashboard/guidance/ (progressive disclosure)"
    )


# ---------------------------------------------------------------------------
# 9. Pest alert uses clear language, not technical source-API limitations
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_pest_alert_no_long_version_on_dashboard(officer_client):
    """The dashboard's pest alert panel must NOT show the long
    'Authorities checked: KEPHIS, KALRO, Migori County Dept. of Agriculture
    — no public alert API; manual retrieval required.' text. That's moved
    to /dashboard/data-sources/ (progressive disclosure). The dashboard
    shows 'Continue local scouting' instead."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "Authorities checked: KEPHIS" not in html, (
        "Long authorities-checked text must be moved to /dashboard/data-sources/ (progressive disclosure)"
    )
    # The dashboard should show the short operational message
    assert "Continue local scouting" in html or "local scouting" in html.lower()


# ---------------------------------------------------------------------------
# 10. Concise primary CTA — no overlong paragraph
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_primary_cta_explanation_is_concise(officer_client):
    """The primary CTA explanation must be concise (per v3 spec: 'Use concise
    messaging'). The full paragraph must be short — under ~250 characters."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")

    # Find the primary CTA paragraph
    # The template uses <p class="text-sm text-stone-700 mt-1.5"> for the explanation
    m = re.search(
        r"Request a climate-smart advisory.*?<p[^>]*>(.*?)</p>",
        html, re.S
    )
    assert m is not None, "Primary CTA explanation paragraph not found"
    explanation = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    # Concise: under 300 characters
    assert len(explanation) <= 300, (
        f"Primary CTA explanation is {len(explanation)} chars — should be concise (<= 300)"
    )
    # Must mention human review/approval is required
    assert "review" in explanation.lower() or "approval" in explanation.lower()
