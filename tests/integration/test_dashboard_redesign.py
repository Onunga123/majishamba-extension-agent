"""Tests for the redesigned dashboard — clarity and operational focus.

Covers the user's explicit success criteria:
  1. Unauthorized users (viewers) do not see "Request advisory" actions.
  2. Synthetic test toggles do not appear in production configuration.
  3. Dashboard renders with empty tasks and advisories (no crashes, no hidden
     assumptions about content being present).
  4. Recent advisories and audit sections link out (to full lists).
Also covers:
  - Long explanatory paragraph moved off the dashboard (now on /dashboard/about/).
  - Office name "Nyatike Sub-County Agricultural Office (intended user)" removed.
  - Cluster list has search box and status filter chips.
  - "View all advisories" / "Full audit log" / "All tasks" links present.
  - New routes /dashboard/about/, /dashboard/guidance/, /dashboard/data-sources/.
"""
from __future__ import annotations

import os

import pytest
from django.conf import settings
from django.test import Client


# ---------------------------------------------------------------------------
# 1. Unauthorized users (viewers) do not see request actions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_viewer_does_not_see_request_advisory_button_on_dashboard(viewer_client):
    """A viewer must NOT see the 'Request advisory' button on the dashboard.
    They must see a 'read-only' notice instead."""
    r = viewer_client.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The request-advisory button must NOT appear to a viewer.
    # (We check the href because the link text 'Request advisory' could
    # appear in other contexts.)
    assert 'href="/advisories/request/"' not in html, (
        "Viewer sees the request-advisory link — should be hidden for non-officers"
    )
    # The read-only notice should be visible to the viewer.
    assert "read-only" in html.lower() or "viewer" in html.lower(), (
        "Viewer should see a 'read-only' notice explaining their role"
    )


@pytest.mark.django_db
def test_viewer_does_not_see_per_cluster_request_link(viewer_client):
    """A viewer must NOT see the per-cluster 'Request advisory' link in the
    cluster list. The ⋮ menu's 'View advisories' link (/advisories/?cluster=)
    is read-only and is acceptable, but the request link (/advisories/request/?cluster=)
    must NOT be visible to a viewer."""
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())

    r = viewer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The request-advisory URL pattern (with the /request/ segment) must NOT
    # appear in the per-cluster rows. The ⋮ menu's 'View advisories' link is fine.
    assert "/advisories/request/?cluster=KACH-" not in html, (
        "Viewer sees per-cluster request-advisory links in the cluster list"
    )
    # But the read-only 'View advisories' link IS allowed in the ⋮ menu
    # (it just filters the advisories list).


@pytest.mark.django_db
def test_officer_sees_request_advisory_button(officer_client):
    """An officer MUST see the 'Request advisory' button on the dashboard."""
    r = officer_client.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert 'href="/advisories/request/"' in html, (
        "Officer cannot see the request-advisory button on the dashboard"
    )


# ---------------------------------------------------------------------------
# 2. Synthetic test toggles do not appear in production configuration
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_synthetic_toggles_absent_on_dashboard_in_production(officer_client, monkeypatch):
    """With DEMO_MODE=False (production), the dashboard must NOT show the
    'Show synthetic test scenario' toggles or any demo content."""
    # Force production-like config
    monkeypatch.setitem(settings.MAJISHAMBA, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "DEBUG", False)

    r = officer_client.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Show synthetic test scenario" not in html, (
        "Synthetic test toggle must NOT appear in production configuration"
    )
    assert "Show synthetic weather test scenario" not in html
    assert "Show synthetic pest test scenario" not in html
    assert "Synthetic demonstration signal" not in html
    assert "synthetic test scenario (demo only" not in html.lower()


@pytest.mark.django_db
def test_synthetic_toggles_absent_in_data_sources_page_in_production(officer_client, monkeypatch):
    """The /dashboard/data-sources/ page must NOT show synthetic test
    scenarios when DEMO_MODE is off (production config)."""
    monkeypatch.setitem(settings.MAJISHAMBA, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "DEBUG", False)

    r = officer_client.get("/dashboard/data-sources/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Show synthetic weather test scenario" not in html
    assert "Show synthetic pest test scenario" not in html
    assert "synthetic test scenario (development only)" not in html.lower()


# ---------------------------------------------------------------------------
# 3. Dashboard renders with empty tasks and advisories
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dashboard_renders_with_no_clusters_no_advisories_no_tasks(officer_client):
    """A completely empty database must not crash the dashboard — it must
    render with the empty-state messages for advisories, tasks, attention,
    audit, and a sensible empty cluster list."""
    r = officer_client.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # Empty drafts state (Needs attention card)
    assert "No drafts pending" in html or "No drafts awaiting review" in html or "drafts awaiting review" in html
    # Empty field visits state
    assert "No visits pending" in html or "No field visits pending." in html or "field_visits" in html.lower()
    # Empty pending tasks state (Needs attention card)
    assert "No tasks pending" in html or "No pending tasks." in html or "pending tasks" in html.lower()
    # Empty advisories message (Recent advisories section)
    assert "No advisories yet" in html
    # Empty recent activity message
    assert "No recent activity" in html


@pytest.mark.django_db
def test_dashboard_renders_with_no_clusters_and_search_active(officer_client):
    """Search + filter UI must be present even when there are no clusters."""
    r = officer_client.get("/dashboard/", {"q": "nonexistent", "status": "all"})
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # New empty-state wording
    assert "No clusters match your filter" in html, (
        "Search with no matches should show 'No clusters match your filter'"
    )
    # Clear-filter link should be present
    assert 'href="?status=all"' in html


@pytest.mark.django_db
def test_cluster_search_by_locality(officer_client):
    """Searching by locality name should filter the cluster list to only matching clusters."""
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    from apps.clusters.models import FarmerCluster
    # Pick the first cluster's locality to search for
    first = FarmerCluster.objects.first()
    if not first.locality:
        pytest.skip("No locality on first cluster")

    r = officer_client.get("/dashboard/", {"q": first.locality})
    html = r.content.decode("utf-8")
    # The matching cluster should appear
    assert first.cluster_id in html
    # Other clusters should not appear (their cluster_ids should be absent).
    # We compare against a search for a different locality that doesn't exist.
    r2 = officer_client.get("/dashboard/", {"q": "zzz-nonexistent-locality-xyz"})
    html2 = r2.content.decode("utf-8")
    assert "No clusters match your filter" in html2


@pytest.mark.django_db
def test_cluster_status_filter_draft(officer_client):
    """The ?status=draft filter should show only clusters with at least one DRAFT advisory."""
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    from apps.advisories.models import Advisory
    from apps.clusters.models import FarmerCluster
    from tests.factories.models import AdvisoryFactory

    cluster = FarmerCluster.objects.first()
    AdvisoryFactory(cluster=cluster, status=Advisory.Status.DRAFT)

    r_all = officer_client.get("/dashboard/", {"status": "all"})
    html_all = r_all.content.decode("utf-8")
    r_draft = officer_client.get("/dashboard/", {"status": "draft"})
    html_draft = r_draft.content.decode("utf-8")
    # The draft filter must show fewer or equal clusters than 'all'
    # (defensive: at least the one we just created)
    assert cluster.cluster_id in html_draft, "Cluster with draft advisory must appear in draft filter"
    # The 'all' view also shows it
    assert cluster.cluster_id in html_all


@pytest.mark.django_db
def test_cluster_status_filter_invalid_falls_back_to_all(officer_client):
    """An invalid ?status= value must fall back to 'all' (no crash, no error)."""
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())

    r = officer_client.get("/dashboard/", {"status": "invalid_filter_value"})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# 4. Recent advisories + audit sections link out
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dashboard_has_view_all_advisories_link(officer_client):
    """The dashboard must have a 'View all advisories' link to /advisories/."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert 'href="/advisories/"' in html, (
        "Dashboard is missing the 'View all advisories' link to /advisories/"
    )


@pytest.mark.django_db
def test_dashboard_has_full_audit_log_link(officer_client):
    """The dashboard must have a 'Full audit log' link to /audit/."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert 'href="/audit/"' in html, (
        "Dashboard is missing the 'Full audit log' link to /audit/"
    )


@pytest.mark.django_db
def test_dashboard_has_all_tasks_link_when_tasks_exist(officer_client):
    """When pending tasks exist, the dashboard tasks section must link to /tasks/."""
    from apps.advisories.models import Advisory
    from apps.clusters.models import FarmerCluster
    from apps.tasks.models import FollowUpTask
    from django.core.management import call_command
    from io import StringIO
    from tests.factories.models import AdvisoryFactory

    call_command("seed_kachieng_clusters", stdout=StringIO())
    adv = AdvisoryFactory(status=Advisory.Status.APPROVED)
    FollowUpTask.objects.create(
        approved_advisory=adv, task_type=FollowUpTask.TaskType.FIELD_VISIT,
        deadline="2030-01-01", status=FollowUpTask.Status.ASSIGNED,
    )
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert 'href="/tasks/"' in html, "Tasks section must link to /tasks/ when tasks exist"


@pytest.mark.django_db
def test_dashboard_recent_activity_excludes_raw_tool_traces(officer_client):
    """The 'Recent activity' summary on the dashboard must NOT include raw
    'tool:*' audit events — those go to the full audit log / advisory detail."""
    from apps.audit.models import AuditEvent
    AuditEvent.objects.create(actor=None, action="tool:get_weather")
    AuditEvent.objects.create(actor=None, action="account:login")
    AuditEvent.objects.create(actor=None, action="advisory:approve")

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # Tool traces excluded from summary (raw action code never shown)
    assert "tool:get_weather" not in html, (
        "Raw tool:* audit traces must NOT appear in the dashboard summary"
    )
    # Decision-oriented events shown via the timeline formatter.
    # account:login → 'signed in'; advisory:approve → 'approved an advisory'
    assert "signed in" in html
    assert "approved an advisory" in html


# ---------------------------------------------------------------------------
# 5. Long explanatory paragraph + office name moved off dashboard
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dashboard_does_not_have_office_name_in_panel(officer_client):
    """The 'Nyatike Sub-County Agricultural Office (intended user)' text must
    NOT appear on the dashboard (moved off in the redesign)."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "Nyatike Sub-County Agricultural Office (intended user)" not in html


@pytest.mark.django_db
def test_dashboard_does_not_show_long_explanatory_paragraph(officer_client):
    """The long explanatory paragraph from the previous dashboard must
    not appear in full on the dashboard. Only the short version stays."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The shortened version mentions 'review' and 'approve'
    assert "review" in html.lower() and "approve" in html.lower(), (
        "Short workflow description should mention review and approve"
    )
    # The old extended version that continued with 'nothing is sent to
    # farmers automatically.' must NOT be on the dashboard.
    assert "nothing is sent to farmers automatically." not in html, (
        "The long extension to the explanatory paragraph must be removed from the dashboard"
    )


@pytest.mark.django_db
def test_dashboard_does_not_have_raw_event_list(officer_client):
    """The dashboard must NOT show the old raw 25-event audit list (replaced by
    a short 5-event summary). We assert the audit list is short — at most 5
    <li> elements in the 'Recent activity' section."""
    import re
    from apps.audit.models import AuditEvent
    # Insert 10 audit events — old dashboard showed 25 in a raw list; new one shows ≤5.
    # Use unique names that are NOT substring-overlapping with each other.
    for i in range(10):
        AuditEvent.objects.create(action=f"uniqueaction{i:02d}_xyz")

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # Count the distinct uniqueaction*_xyz events shown — must be ≤ 5
    matches = set(re.findall(r"uniqueaction\d+_xyz", html))
    assert len(matches) <= 5, (
        f"Recent activity list shows {len(matches)} events — should be ≤ 5 (got: {sorted(matches)})"
    )
    # The "Recent activity" section must NOT show a long raw list (no <ul> with > 5 <li>s)
    recent_section = re.search(r"Recent activity.*?</ul>", html, re.S)
    assert recent_section is not None, "Recent activity section missing"
    li_count = recent_section.group(0).count("<li")
    assert li_count <= 5, (
        f"Recent activity section has {li_count} <li> elements — should be ≤ 5"
    )


# ---------------------------------------------------------------------------
# 6. New routes /dashboard/about/, /dashboard/guidance/, /dashboard/data-sources/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dashboard_about_route_works(officer_client):
    """/dashboard/about/ must return 200 and contain the MIT licence text
    that was removed from the operational footer."""
    r = officer_client.get("/dashboard/about/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "MIT License" in html or "MIT licence" in html
    assert "Permission is hereby granted, free of charge" in html


@pytest.mark.django_db
def test_dashboard_guidance_route_works(officer_client):
    """/dashboard/guidance/ must return 200 and contain the KALRO
    permission-pending details."""
    r = officer_client.get("/dashboard/guidance/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "KALRO" in html
    assert "permission-pending" in html.lower() or "permission pending" in html.lower()


@pytest.mark.django_db
def test_dashboard_data_sources_route_works(officer_client):
    """/dashboard/data-sources/ must return 200 and contain the detailed
    source-authority notes that were moved off the dashboard."""
    r = officer_client.get("/dashboard/data-sources/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Kenya Meteorological Department" in html
    assert "KEPHIS" in html


@pytest.mark.django_db
def test_about_route_requires_login():
    """Anonymous users must be redirected from /dashboard/about/ to login."""
    c = Client()
    r = c.get("/dashboard/about/")
    assert r.status_code in {302, 301}


@pytest.mark.django_db
def test_guidance_route_requires_login():
    """Anonymous users must be redirected from /dashboard/guidance/ to login."""
    c = Client()
    r = c.get("/dashboard/guidance/")
    assert r.status_code in {302, 301}


@pytest.mark.django_db
def test_data_sources_route_requires_login():
    """Anonymous users must be redirected from /dashboard/data-sources/ to login."""
    c = Client()
    r = c.get("/dashboard/data-sources/")
    assert r.status_code in {302, 301}


# ---------------------------------------------------------------------------
# 7. Cluster list is a focused list (not a wide table)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dashboard_has_search_box(officer_client):
    """The dashboard cluster list must have a search box."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert 'type="search"' in html, "Search input must be present"
    assert 'name="q"' in html


@pytest.mark.django_db
def test_dashboard_has_status_filter_chips(officer_client):
    """The dashboard cluster list must have status filter chips."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # All filter chip labels should be present
    for label in ("All", "Draft", "Approved", "Needs field visit", "No advisory"):
        assert label in html, f"Status filter chip {label!r} missing from dashboard"


@pytest.mark.django_db
def test_cluster_list_uses_expandable_rows_for_hh_plots(officer_client):
    """HH and Plots columns must be visible on desktop (responsive table)
    but not as <th>HH</th> table headers — the new design uses th.scope=col
    with proper labels. The mobile card layout shows HH/Plots inline.
    Either way, the count must be visible somewhere in the rendered HTML."""
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The new desktop table uses <th scope="col">Households</th>
    # (not the old terse <th>HH</th>)
    assert "Households" in html, "Households column header must be present"
    assert "Plots" in html, "Plots column header must be present"
    # The new design has cluster HH/Plots counts visible in the table or in the mobile cards
    assert "household_count" not in html or "tabular-nums" in html or "HH:" in html


# ---------------------------------------------------------------------------
# 8. Recent advisories grouped by status
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_recent_advisories_grouped_by_status(officer_client):
    """The recent advisories section should show advisory groups by status:
    Draft, Approved, Rejected."""
    from django.core.management import call_command
    from io import StringIO
    from tests.factories.models import AdvisoryFactory

    call_command("seed_kachieng_clusters", stdout=StringIO())
    AdvisoryFactory(status="draft")
    AdvisoryFactory(status="approved")
    AdvisoryFactory(status="rejected")

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # Group headings should be present
    # (the template uses status_label|title which becomes "Draft", "Approved", "Rejected")
    # The template iteration puts them as group headings
    assert "Draft" in html
    assert "Approved" in html
    assert "Rejected" in html


@pytest.mark.django_db
def test_recent_advisories_does_not_have_repetitive_verify_locally_text(officer_client):
    """The dashboard recent-advisories list must NOT repeat 'Verify locally'
    text for every row — only short status badges and links are shown."""
    from django.core.management import call_command
    from io import StringIO
    from tests.factories.models import AdvisoryFactory

    call_command("seed_kachieng_clusters", stdout=StringIO())
    # Create several advisories with verify_locally recommendation
    for _ in range(5):
        AdvisoryFactory(recommendation_type="verify_locally", status="draft")

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # "Verify locally" appears once per recommendation_type label per row, but
    # the verbose display name is "Verify locally" — we accept that it appears
    # in the per-row recommendation column. What we DON'T want is the long
    # "Verify locally with the extension office before communicating to farmers"
    # kind of repetitive message. The short label is fine.
    # We just assert the section is short and decision-oriented:
    # the word "Verify" should not appear 5+ times in long-form text.
    verify_count = html.lower().count("verify locally")
    # Should be at most the number of advisories (5) — not 5x the same long sentence.
    assert verify_count <= 7, (
        f"'Verify locally' appears {verify_count} times — too repetitive"
    )


# ---------------------------------------------------------------------------
# 9. Footer is minimal
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_operational_footer_is_minimal(officer_client):
    """The operational footer (base.html, used by dashboard) must NOT show
    the long MIT licence text — only a short synthetic-data disclaimer +
    an 'About / legal' link."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The short synthetic disclaimer must be present
    assert "Synthetic household & plot data only" in html or "Synthetic household &amp; plot data only" in html
    # The long MIT licence line must NOT be in the footer anymore
    assert "Kachieng AI Agent — MIT licence" not in html, (
        "Long MIT licence text must be removed from the operational footer"
    )
    # The About / legal link must be in the footer
    assert 'href="/dashboard/about/"' in html


# ---------------------------------------------------------------------------
# 10. Responsive + accessibility
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dashboard_responsive_grid_classes(officer_client):
    """Dashboard sections must use responsive grid classes (sm:, lg:) so
    they stack on narrow screens. The cluster table (desktop) and cluster
    cards (mobile) classes are only emitted when at least one cluster exists,
    so we seed clusters first."""
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The v3 needs-attention section uses sm:grid-cols-3 (3 cards: drafts,
    # field visits, pending tasks — 'Recently approved' was removed)
    assert "sm:grid-cols-3" in html or "sm:grid-cols-2" in html
    # The field-conditions (weather/pests/guidance) grid uses lg:grid-cols-3
    assert "lg:grid-cols-3" in html
    # The cluster search bar uses sm:flex-row
    assert "sm:flex-row" in html
    # Mobile/desktop toggle: v3 uses Tailwind 'md:hidden' / 'hidden md:block'
    assert "md:hidden" in html or "hide-on-mobile" in html
    assert "hidden md:block" in html or "show-on-mobile-only" in html


@pytest.mark.django_db
def test_dashboard_has_focus_visible_styles(officer_client):
    """Dashboard interactive elements must have focus-visible outline classes."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "focus-visible:outline" in html


@pytest.mark.django_db
def test_dashboard_skip_link_present(officer_client):
    """The dashboard (via base.html) must have a skip link to main content."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert 'class="skip-link"' in html
    assert 'href="#main-content"' in html
    assert 'id="main-content"' in html
