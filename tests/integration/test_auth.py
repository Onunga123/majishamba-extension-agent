"""Tests for authentication, registration, and account approval."""
from __future__ import annotations

import pytest
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_anonymous_users_see_no_operational_navbar():
    """Anonymous users should only see Sign in / Create account — no operational nav."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "Sign in" in html
    assert "Create account" in html or "Request access" in html
    assert "Dashboard" not in html
    assert "Advisories" not in html
    assert "Tasks" not in html
    assert "Audit" not in html
    assert "Data" not in html


@pytest.mark.django_db
def test_demo_cards_completely_absent():
    """No demo account cards should appear on the login page — ever, regardless of DEMO_MODE."""
    from django.conf import settings
    # Even with DEMO_MODE=True and DEBUG=True, demo cards must not appear.
    settings.MAJISHAMBA["DEMO_MODE"] = True
    settings.DEBUG = True
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "Choose a demo account" not in html
    assert "Synthetic demo account" not in html
    assert "Demo mode is ON" not in html
    assert "demo" not in html.lower() or "demo" not in " ".join(html.split())


@pytest.mark.django_db
def test_registration_creates_pending_account_not_privileged():
    """Registration creates a PENDING account with viewer role — no operational access."""
    c = Client()
    r = c.post("/accounts/register/", {
        "username": "newofficer",
        "full_name": "New Officer",
        "email": "new@example.com",
        "requested_role": "supervisor",
        "organization": "Nyatike Office",
        "sub_county": "Nyatike",
        "ward": "Kachieng",
        "password1": "strong-password-123",
        "password2": "strong-password-123",
    })
    assert r.status_code == 302
    user = User.objects.get(username="newofficer")
    assert user.approval_status == "pending"
    assert user.role == "viewer"
    assert user.requested_role == "supervisor"
    assert user.is_staff is False
    assert user.is_superuser is False


@pytest.mark.django_db
def test_form_tampering_cannot_create_staff_or_superuser():
    """POST with is_staff=true or is_superuser=true must NOT grant those flags."""
    c = Client()
    r = c.post("/accounts/register/", {
        "username": "hacker",
        "full_name": "Hacker",
        "email": "",
        "requested_role": "extension_officer",
        "organization": "",
        "sub_county": "Nyatike",
        "ward": "Kachieng",
        "password1": "hacker-password-1",
        "password2": "hacker-password-1",
        "is_staff": "true",
        "is_superuser": "true",
        "role": "supervisor",
    })
    assert r.status_code == 302
    user = User.objects.get(username="hacker")
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.role == "viewer"


@pytest.mark.django_db
def test_requested_role_distinct_from_effective():
    """requested_role is stored separately from the effective role."""
    c = Client()
    c.post("/accounts/register/", {
        "username": "role_test",
        "full_name": "Role Test",
        "email": "",
        "requested_role": "supervisor",
        "organization": "",
        "sub_county": "Nyatike",
        "ward": "Kachieng",
        "password1": "role-test-password-1",
        "password2": "role-test-password-1",
    })
    user = User.objects.get(username="role_test")
    assert user.requested_role == "supervisor"
    assert user.role == "viewer"  # different


@pytest.mark.django_db
def test_password_mismatch_rejected():
    """Passwords that don't match are rejected."""
    c = Client()
    r = c.post("/accounts/register/", {
        "username": "badpw", "full_name": "Bad PW", "email": "",
        "requested_role": "viewer", "organization": "",
        "sub_county": "Nyatike", "ward": "Kachieng",
        "password1": "password-one-123", "password2": "password-two-456",
    })
    assert r.status_code == 200
    assert not User.objects.filter(username="badpw").exists()


@pytest.mark.django_db
def test_short_password_rejected():
    """Passwords shorter than 10 characters are rejected."""
    c = Client()
    r = c.post("/accounts/register/", {
        "username": "shortpw", "full_name": "Short PW", "email": "",
        "requested_role": "viewer", "organization": "",
        "sub_county": "Nyatike", "ward": "Kachieng",
        "password1": "short", "password2": "short",
    })
    assert r.status_code == 200
    assert not User.objects.filter(username="shortpw").exists()


@pytest.mark.django_db
def test_account_review_requires_supervisor():
    """Only supervisors/staff can access the account review page."""
    c = Client()
    r = c.get("/accounts/review/")
    assert r.status_code in {302, 301}


@pytest.mark.django_db
def test_viewer_cannot_access_account_review(viewer_client):
    """A viewer cannot access the account review page."""
    r = viewer_client.get("/accounts/review/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_supervisor_can_approve_account(supervisor):
    """A supervisor can approve a pending account with the correct role."""
    pending = User.objects.create(
        username="pending1", full_name="Pending One", role="viewer",
        requested_role="extension_officer", approval_status="pending", is_active=True,
    )
    c = Client()
    c.force_login(supervisor)
    r = c.post(f"/accounts/review/{pending.id}/approve/", {"effective_role": "extension_officer"})
    assert r.status_code == 302
    pending.refresh_from_db()
    assert pending.approval_status == "approved"
    assert pending.role == "extension_officer"
    assert pending.approved_by == supervisor


@pytest.mark.django_db
def test_supervisor_can_reject_account(supervisor):
    """A supervisor can reject a pending account."""
    pending = User.objects.create(
        username="pending2", full_name="Pending Two", role="viewer",
        requested_role="supervisor", approval_status="pending", is_active=True,
    )
    c = Client()
    c.force_login(supervisor)
    r = c.post(f"/accounts/review/{pending.id}/reject/", {"rejection_reason": "Not authorized"})
    assert r.status_code == 302
    pending.refresh_from_db()
    assert pending.approval_status == "rejected"
    assert pending.rejection_reason == "Not authorized"
    assert pending.is_active is False


@pytest.mark.django_db
def test_user_cannot_approve_own_account(supervisor):
    """A user cannot approve their own account."""
    c = Client()
    c.force_login(supervisor)
    r = c.post(f"/accounts/review/{supervisor.id}/approve/", {"effective_role": "supervisor"})
    assert r.status_code == 403


@pytest.mark.django_db
def test_duplicate_registration_rejected():
    """Duplicate username is rejected."""
    User.objects.create(username="existing", is_active=True)
    c = Client()
    r = c.post("/accounts/register/", {
        "username": "existing", "full_name": "Duplicate", "email": "",
        "requested_role": "viewer", "organization": "",
        "sub_county": "Nyatike", "ward": "Kachieng",
        "password1": "dup-password-123", "password2": "dup-password-123",
    })
    assert r.status_code == 200


@pytest.mark.django_db
def test_logout_requires_post():
    """Logout via GET should not work."""
    c = Client(enforce_csrf_checks=True)
    r = c.get("/accounts/logout/")
    assert r.status_code == 405


@pytest.mark.django_db
def test_unsafe_next_redirect_rejected():
    """Login with an external next URL redirects to /dashboard/ instead."""
    from tests.factories.models import OfficerFactory
    user = OfficerFactory(username="testredirect")
    user.set_password("test-password-1")
    user.is_staff = True
    user.save()
    c = Client()
    r = c.post("/accounts/login/?next=https://evil.example.com/", {
        "username": "testredirect", "password": "test-password-1",
    })
    assert r.status_code == 302
    assert "evil.example.com" not in r.url


@pytest.mark.django_db
def test_existing_legitimate_accounts_still_work():
    """Existing approved accounts can still log in."""
    from apps.accounts.models import User as U
    u, _ = U.objects.get_or_create(
        username="nyatike_officer",
        defaults={"role": "extension_officer", "full_name": "Jane Awuor", "sub_county": "Nyatike", "ward": "Kachieng", "is_staff": True},
    )
    u.set_password("majishamba-demo-2025")
    u.save()
    c = Client()
    r = c.post("/accounts/login/", {"username": "nyatike_officer", "password": "majishamba-demo-2025"})
    assert r.status_code == 302


@pytest.mark.django_db
def test_registration_page_accessible_anonymously():
    """The registration page is accessible without authentication."""
    c = Client()
    r = c.get("/accounts/register/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Request access" in html or "Create account" in html
    assert "pending review" in html.lower() or "administrator" in html.lower()


@pytest.mark.django_db
def test_authenticated_user_redirected_from_register():
    """An already-authenticated user is redirected away from the register page."""
    from tests.factories.models import OfficerFactory
    user = OfficerFactory()
    c = Client()
    c.force_login(user)
    r = c.get("/accounts/register/")
    assert r.status_code == 302


@pytest.mark.django_db
def test_direct_operational_access_requires_login():
    """Anonymous users cannot access operational routes directly."""
    c = Client()
    for url in ["/dashboard/", "/advisories/", "/tasks/", "/audit/", "/integrations/"]:
        r = c.get(url)
        assert r.status_code in {302, 301}, f"{url} should require login, got {r.status_code}"


@pytest.mark.django_db
def test_login_page_no_demo_hints():
    """The login page must not contain demo passwords or hints."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "majishamba-demo" not in html
    assert "nyatike_officer" not in html
    assert "nyatike_supervisor" not in html
    assert "nyatike_viewer" not in html
    assert "Demo mode" not in html
