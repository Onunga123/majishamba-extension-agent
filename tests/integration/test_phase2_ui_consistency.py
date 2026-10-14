"""Phase 2 regression tests — page-heading and metadata consistency.

Tests that all pages identified in Phase 2 use the established
text-2xl heading convention, have separated metadata where applicable,
and have appropriately sized buttons. Also tests that the account review
table has a horizontal-scroll wrapper for mobile.
"""
from __future__ import annotations

import pytest
from django.test import Client


# ---------------------------------------------------------------------------
# 1. Task detail — heading, metadata separation, button sizing
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_task_detail_heading_is_text_2xl(officer_client):
    from tests.factories.models import AdvisoryFactory
    from apps.tasks.models import FollowUpTask

    a = AdvisoryFactory(status="approved")
    task = FollowUpTask.objects.create(
        approved_advisory=a,
        task_type="field_visit",
        status="assigned",
        deadline="2026-11-01",
    )
    r = officer_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert 'class="text-2xl font-semibold text-stone-900"' in html
    assert f"Follow-up task {task.id}" in html


@pytest.mark.django_db
def test_task_detail_has_page_header(officer_client):
    from tests.factories.models import AdvisoryFactory
    from apps.tasks.models import FollowUpTask

    a = AdvisoryFactory(status="approved")
    task = FollowUpTask.objects.create(
        approved_advisory=a, task_type="field_visit", status="assigned",
    )
    r = officer_client.get(f"/tasks/{task.id}/")
    html = r.content.decode("utf-8")
    assert '<header class="mb-6">' in html


@pytest.mark.django_db
def test_task_detail_metadata_is_separated(officer_client):
    from tests.factories.models import AdvisoryFactory
    from apps.tasks.models import FollowUpTask

    a = AdvisoryFactory(status="approved")
    task = FollowUpTask.objects.create(
        approved_advisory=a, task_type="field_visit", status="assigned",
    )
    r = officer_client.get(f"/tasks/{task.id}/")
    html = r.content.decode("utf-8")
    # Metadata should use <dl> with <dt>/<dd> pairs, not inline concatenated text
    assert "<dl" in html
    assert "<dt" in html
    assert "<dd" in html
    # Check that key labels are present as separate elements
    for label in ["Type", "Status", "Deadline", "Cluster", "Advisory"]:
        assert f">{label}<" in html, f"Metadata label '{label}' must be a separate element"


@pytest.mark.django_db
def test_task_detail_save_findings_button_has_44px(officer_client):
    from tests.factories.models import AdvisoryFactory
    from apps.tasks.models import FollowUpTask

    a = AdvisoryFactory(status="approved")
    task = FollowUpTask.objects.create(
        approved_advisory=a, task_type="field_visit", status="assigned",
    )
    r = officer_client.get(f"/tasks/{task.id}/")
    html = r.content.decode("utf-8")
    assert "min-h-[44px]" in html
    assert "Save findings" in html


@pytest.mark.django_db
def test_task_detail_form_action_preserved(officer_client):
    from tests.factories.models import AdvisoryFactory
    from apps.tasks.models import FollowUpTask

    a = AdvisoryFactory(status="approved")
    task = FollowUpTask.objects.create(
        approved_advisory=a, task_type="field_visit", status="assigned",
    )
    r = officer_client.get(f"/tasks/{task.id}/")
    html = r.content.decode("utf-8")
    assert f'action="/tasks/{task.id}/findings/"' in html
    assert "{% csrf_token %}" not in html  # Must be rendered, not raw
    assert "csrfmiddlewaretoken" in html  # CSRF token must be present


# ---------------------------------------------------------------------------
# 2. Cluster detail — heading, metadata separation, button sizing
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cluster_detail_heading_is_text_2xl(officer_client):
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/clusters/KACH-02/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert 'class="text-2xl font-semibold text-stone-900"' in html


@pytest.mark.django_db
def test_cluster_detail_has_page_header(officer_client):
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/clusters/KACH-02/")
    html = r.content.decode("utf-8")
    assert '<header class="mb-6">' in html


@pytest.mark.django_db
def test_cluster_detail_request_advisory_button_has_44px(officer_client):
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/clusters/KACH-02/")
    html = r.content.decode("utf-8")
    assert "min-h-[44px]" in html
    assert "Request advisory" in html


@pytest.mark.django_db
def test_cluster_detail_metadata_is_separated(officer_client):
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/clusters/KACH-02/")
    html = r.content.decode("utf-8")
    assert "<dl" in html
    assert "<dt" in html
    assert "<dd" in html
    for label in ["Locality", "Cluster code"]:
        assert f">{label}<" in html


# ---------------------------------------------------------------------------
# 3. Account review — heading, table overflow wrapper, button sizing
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_account_review_heading_is_text_2xl(system_admin):
    c = Client()
    c.force_login(system_admin)
    r = c.get("/accounts/review/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert 'class="text-2xl font-semibold text-stone-900"' in html


@pytest.mark.django_db
def test_account_review_table_has_overflow_wrapper(system_admin):
    from apps.accounts.models import User
    # Create a pending account so the table is rendered
    User.objects.get_or_create(
        username="pending_overflow_test",
        defaults={
            "role": User.Role.VIEWER,
            "full_name": "Pending Overflow",
            "approval_status": "pending",
            "requested_role": "extension_officer",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
        },
    )
    c = Client()
    c.force_login(system_admin)
    r = c.get("/accounts/review/")
    html = r.content.decode("utf-8")
    assert 'overflow-x-auto' in html, "Account review table must have overflow-x-auto wrapper"


@pytest.mark.django_db
def test_account_review_approve_button_has_44px(system_admin):
    from apps.accounts.models import User
    # Create a pending account
    User.objects.get_or_create(
        username="pending_test_user",
        defaults={
            "role": User.Role.VIEWER,
            "full_name": "Pending User",
            "approval_status": "pending",
            "requested_role": "extension_officer",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
        },
    )
    c = Client()
    c.force_login(system_admin)
    r = c.get("/accounts/review/")
    html = r.content.decode("utf-8")
    assert "min-h-[44px]" in html, "Approve/Reject buttons must have min-h-[44px]"
    assert "Approve" in html


@pytest.mark.django_db
def test_account_review_reject_button_has_44px(system_admin):
    from apps.accounts.models import User
    User.objects.get_or_create(
        username="pending_test_user2",
        defaults={
            "role": User.Role.VIEWER,
            "full_name": "Pending User 2",
            "approval_status": "pending",
            "requested_role": "extension_officer",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
        },
    )
    c = Client()
    c.force_login(system_admin)
    r = c.get("/accounts/review/")
    html = r.content.decode("utf-8")
    assert "min-h-[44px]" in html
    assert "Reject" in html


# ---------------------------------------------------------------------------
# 4. Create user — heading, button sizing, Cancel styling
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_user_heading_is_text_2xl(system_admin):
    c = Client()
    c.force_login(system_admin)
    r = c.get("/accounts/users/create/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert 'class="text-2xl font-semibold text-stone-900"' in html


@pytest.mark.django_db
def test_create_user_submit_button_has_44px(system_admin):
    c = Client()
    c.force_login(system_admin)
    r = c.get("/accounts/users/create/")
    html = r.content.decode("utf-8")
    assert "min-h-[44px]" in html


@pytest.mark.django_db
def test_create_user_cancel_is_rectangular(system_admin):
    c = Client()
    c.force_login(system_admin)
    r = c.get("/accounts/users/create/")
    html = r.content.decode("utf-8")
    assert "border border-stone-300" in html
    # The old plain-text Cancel must NOT be present
    assert 'class="text-sm text-stone-600 hover:underline">Cancel' not in html


# ---------------------------------------------------------------------------
# 5. Profile — title block, heading, metadata separation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_profile_has_title_block(officer_client):
    r = officer_client.get("/accounts/profile/")
    html = r.content.decode("utf-8")
    assert "<title>Profile" in html, "Profile page must have a {% block title %}"


@pytest.mark.django_db
def test_profile_heading_is_text_2xl(officer_client):
    r = officer_client.get("/accounts/profile/")
    html = r.content.decode("utf-8")
    assert 'class="text-2xl font-semibold text-stone-900"' in html


@pytest.mark.django_db
def test_profile_has_page_header(officer_client):
    r = officer_client.get("/accounts/profile/")
    html = r.content.decode("utf-8")
    assert '<header class="mb-6">' in html


# ---------------------------------------------------------------------------
# 6. Remaining heading consistency — data_sources, about, agent
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_data_sources_heading_is_text_2xl(officer_client):
    r = officer_client.get("/dashboard/data-sources/")
    html = r.content.decode("utf-8")
    assert 'class="text-2xl font-semibold text-stone-900"' in html


@pytest.mark.django_db
def test_about_heading_is_text_2xl(officer_client):
    r = officer_client.get("/dashboard/about/")
    html = r.content.decode("utf-8")
    assert 'class="text-2xl font-semibold text-stone-900"' in html


@pytest.mark.django_db
def test_agent_heading_is_text_2xl(officer_client):
    r = officer_client.get("/agents/graph/")
    html = r.content.decode("utf-8")
    assert 'class="text-2xl font-semibold text-stone-900"' in html
