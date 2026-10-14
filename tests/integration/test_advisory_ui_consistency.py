"""Integration tests for the standardised advisory presentation.

Verifies that all advisory-related pages use the same .ar-* design
system, the same hero header pattern, the same audit footer chips,
and the same button hierarchy. Run with:
    pytest tests/integration/test_advisory_ui_consistency.py
"""
from __future__ import annotations

import pytest
from django.test import Client


# ---------------------------------------------------------------------------
# 1. List page uses the .ar-* design system
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_advisory_list_uses_ar_design_system(officer_client):
    """The advisories list page must use the .ar-* class system and load
    the page-scoped advisory_detail_v2.css stylesheet.
    """
    r = officer_client.get("/advisories/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # Page-scoped CSS must be loaded
    assert "advisory_detail_v2.css" in html
    # Page header
    assert 'class="ar-list-header"' in html
    assert "<h1>Advisories</h1>" in html
    # Filter form
    assert 'class="ar-filter-form"' in html
    # Status filter chips
    assert 'class="ar-status-chips"' in html
    assert 'ar-status-chip' in html
    # Table
    assert 'class="ar-table"' in html
    # Request advisory button uses the .ar-btn--primary class
    assert "ar-btn ar-btn--primary" in html
    assert "Request advisory" in html


@pytest.mark.django_db
def test_advisory_list_has_search_and_sort(on_officer_client_with_advisories):
    """The list page must have a search input, status filter, and sort
    links on ID/Locality/Cluster/Status columns.
    """
    r = on_officer_client_with_advisories.get("/advisories/")
    html = r.content.decode("utf-8")
    assert 'id="advisory-search"' in html
    assert 'name="status"' in html
    assert "sort=id" in html or "sort=-id" in html
    assert "sort=cluster__locality" in html
    assert "sort=cluster__cluster_id" in html
    assert "sort=status" in html


# ---------------------------------------------------------------------------
# 2. Detail page uses the .ar-* design system
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_advisory_detail_uses_ar_design_system(officer_client):
    """The advisory detail page must use the .ar-* class system and load
    the page-scoped stylesheet.
    """
    from tests.factories.models import AdvisoryFactory
    a = AdvisoryFactory(status="draft")
    r = officer_client.get(f"/advisories/{a.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "advisory_detail_v2.css" in html
    assert 'class="ar-page"' in html
    assert 'class="ar-hero"' in html
    assert 'class="ar-hero__title"' in html
    # Hero metadata uses the shared partial (_hero_meta.html)
    assert 'class="ar-hero__meta"' in html
    assert 'class="ar-hero__meta-label"' in html
    # Audit footer uses the shared partial (_audit_footer.html)
    assert 'class="ar-audit"' in html
    assert 'class="ar-audit-item"' in html
    assert 'class="ar-audit-label"' in html


# ---------------------------------------------------------------------------
# 3. Edit page uses the .ar-* design system
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_advisory_edit_uses_ar_design_system(officer_client):
    """The edit page must use the .ar-* class system and load the
    page-scoped stylesheet.
    """
    from tests.factories.models import AdvisoryFactory
    a = AdvisoryFactory(status="draft")
    r = officer_client.get(f"/advisories/{a.id}/edit/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "advisory_detail_v2.css" in html
    assert 'class="ar-hero"' in html
    assert 'class="ar-hero__title"' in html
    # Form uses the .ar-decision-form class
    assert 'class="ar-decision-form"' in html or 'ar-decision-form' in html
    # Save draft button uses the .ar-btn--primary class
    assert "ar-btn ar-btn--primary" in html
    assert "Save draft" in html
    # Cancel button uses .ar-btn--secondary
    assert "ar-btn ar-btn--secondary" in html
    assert "Cancel" in html


# ---------------------------------------------------------------------------
# 4. Request page uses the .ar-* design system
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_advisory_request_uses_ar_design_system(officer_client):
    """The request page must use the .ar-* class system and load the
    page-scoped stylesheet.
    """
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/advisories/request/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "advisory_detail_v2.css" in html
    assert 'class="ar-hero"' in html
    assert "<h1>Request advisory</h1>" in html or "Request advisory" in html
    # Start advisory run button uses .ar-btn--primary
    assert "ar-btn ar-btn--primary" in html
    assert "Start advisory run" in html


# ---------------------------------------------------------------------------
# 5. Deleted page uses the .ar-* design system
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_advisory_deleted_uses_ar_design_system(supervisor_client):
    """The deleted-advisories page must use the .ar-* class system and
    load the page-scoped stylesheet.
    """
    r = supervisor_client.get("/advisories/deleted/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "advisory_detail_v2.css" in html
    assert 'class="ar-list-header"' in html
    assert "Deleted advisories" in html
    # Info notice uses the .ar-gen-notice class
    assert 'class="ar-gen-notice"' in html or 'ar-gen-notice' in html


# ---------------------------------------------------------------------------
# 6. Approval gate page uses the .ar-* design system (already established)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_approval_gate_uses_ar_design_system(supervisor_client):
    """The approval gate page must use the .ar-* class system.
    """
    from tests.factories.models import AdvisoryFactory
    a = AdvisoryFactory(status="draft")
    r = supervisor_client.get(f"/approvals/{a.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "advisory_detail_v2.css" in html
    assert 'class="ar-hero"' in html
    assert 'class="ar-audit-item"' in html
    # Submit decision uses .ar-btn--primary
    assert "Submit decision" in html
    assert "ar-btn ar-btn--primary" in html


# ---------------------------------------------------------------------------
# 7. Shared partials render the same content on every page
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_hero_meta_partial_renders_metadata_consistently(officer_client, supervisor_client):
    """The _hero_meta.html partial must render Cluster / Crop / Season /
    Version with the same .ar-hero__meta-label and .ar-hero__meta-value
    classes on the detail and edit pages.

    Note: the approval gate page intentionally omits the hero metadata
    block (the metadata appears only in the Advisory scope tile to
    avoid duplication, per the user's previous instruction).
    """
    from tests.factories.models import AdvisoryFactory
    a = AdvisoryFactory(status="draft")
    # Detail page
    r1 = officer_client.get(f"/advisories/{a.id}/")
    html1 = r1.content.decode("utf-8")
    # Edit page
    r2 = officer_client.get(f"/advisories/{a.id}/edit/")
    html2 = r2.content.decode("utf-8")

    for html, label in [(html1, "detail"), (html2, "edit")]:
        assert 'class="ar-hero__meta"' in html, f"hero meta missing on {label}"
        assert 'class="ar-hero__meta-label"' in html, f"hero meta label missing on {label}"
        assert 'class="ar-hero__meta-value"' in html, f"hero meta value missing on {label}"
        # All four metadata fields must be present
        for field in ["Cluster", "Crop", "Season", "Version"]:
            assert field in html, f"hero meta field '{field}' missing on {label}"


@pytest.mark.django_db
def test_audit_footer_partial_renders_three_fields(officer_client, supervisor_client):
    """The _audit_footer.html partial must render Created / Run time /
    By as three separate .ar-audit-item chips on every page that uses it.
    """
    from tests.factories.models import AdvisoryFactory
    a = AdvisoryFactory(status="draft", generation_seconds=4.38)
    # Detail page
    r1 = officer_client.get(f"/advisories/{a.id}/")
    html1 = r1.content.decode("utf-8")
    # Edit page
    r2 = officer_client.get(f"/advisories/{a.id}/edit/")
    html2 = r2.content.decode("utf-8")
    # Approval gate
    r3 = supervisor_client.get(f"/approvals/{a.id}/")
    html3 = r3.content.decode("utf-8")

    for html, label in [(html1, "detail"), (html2, "edit"), (html3, "gate")]:
        assert 'class="ar-audit"' in html, f"audit footer missing on {label}"
        # All three labels must be present
        for field in ["Created", "Run time", "By"]:
            assert f">{field}<" in html or f">{field}:" in html, f"audit field '{field}' missing on {label}"


# ---------------------------------------------------------------------------
# 8. Action button hierarchy is consistent across pages
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_action_button_hierarchy_is_consistent(officer_client, supervisor_client):
    """Review and decide / Submit decision / Save draft / Start run must
    all use the .ar-btn--primary class (filled green) as the principal
    action on their respective pages.
    """
    from tests.factories.models import AdvisoryFactory
    a = AdvisoryFactory(status="draft")
    # Detail page — Review and decide
    r1 = officer_client.get(f"/advisories/{a.id}/")
    assert "Review and decide" in r1.content.decode("utf-8")
    assert "ar-btn ar-btn--primary" in r1.content.decode("utf-8")
    # Edit page — Save draft
    r2 = officer_client.get(f"/advisories/{a.id}/edit/")
    assert "Save draft" in r2.content.decode("utf-8")
    assert "ar-btn ar-btn--primary" in r2.content.decode("utf-8")
    # Approval gate — Submit decision
    r3 = supervisor_client.get(f"/approvals/{a.id}/")
    assert "Submit decision" in r3.content.decode("utf-8")
    assert "ar-btn ar-btn--primary" in r3.content.decode("utf-8")


# ---------------------------------------------------------------------------
# Fixture: officer client with at least one advisory in the list
# ---------------------------------------------------------------------------

@pytest.fixture
def on_officer_client_with_advisories(officer_client):
    from tests.factories.models import AdvisoryFactory
    AdvisoryFactory(status="draft")
    AdvisoryFactory(status="approved")
    return officer_client
