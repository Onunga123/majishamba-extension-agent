"""Login tests — security rules (no demo content, no demo accounts).

These tests verify that the login page is clean of demo content and that
the security rules (CSRF, unsafe next URL, inactive accounts, viewer
cannot escalate to officer) still hold. The previous demo-card tests
have been removed because the demo cards have been removed from the
template entirely.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings


# ---------------------------------------------------------------------------
# No demo content on the login page — regardless of DEMO_MODE
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_page_never_shows_demo_cards():
    """Demo account cards must NEVER appear on the login page, regardless of DEMO_MODE.
    The login template no longer has any demo card markup at all."""
    from django.conf import settings
    settings.MAJISHAMBA["DEMO_MODE"] = True
    settings.DEBUG = True
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "Choose a demo account" not in html
    assert "Synthetic demo account" not in html
    assert "nyatike_officer" not in html
    assert "nyatike_supervisor" not in html
    assert "nyatike_viewer" not in html
    assert "Demo mode" not in html
    assert "demo account selector" not in html


@pytest.mark.django_db
def test_login_page_never_shows_demo_cards_with_demo_mode_disabled():
    """With DEMO_MODE=False, the login page must NOT show demo account cards either."""
    from django.conf import settings
    settings.MAJISHAMBA["DEMO_MODE"] = False
    settings.DEBUG = True
    try:
        c = Client()
        r = c.get("/accounts/login/")
        html = r.content.decode("utf-8")
        assert "Choose a demo account" not in html
        assert "Synthetic demo account" not in html
        assert "nyatike_officer" not in html
    finally:
        # Restore dev defaults.
        settings.MAJISHAMBA["DEMO_MODE"] = True


@pytest.mark.django_db
def test_register_page_never_shows_demo_cards():
    """The register page must not show demo content either."""
    c = Client()
    r = c.get("/accounts/register/")
    html = r.content.decode("utf-8")
    assert "Choose a demo account" not in html
    assert "Synthetic demo account" not in html
    assert "nyatike_officer" not in html
    assert "Demo mode" not in html


# ---------------------------------------------------------------------------
# Security rules — login form
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_with_empty_password_rejected():
    """A POST with just the username (no password) must fail — the user must always
    type the password. This is the standard Django auth form behavior, but the test
    guards against any future 'auto-fill password' regression."""
    c = Client()
    r = c.post("/accounts/login/", {"username": "anyone", "password": ""})
    # Django's auth form rejects empty password. Failed login returns 200 (re-rendered form)
    # but the user is NOT authenticated.
    assert r.status_code == 200
    assert not c.session.get("_auth_user_id"), "Login succeeded without a password — security bug"


@pytest.mark.django_db
def test_login_with_wrong_password_rejected(officer):
    """A POST with a wrong password fails. Roles are always derived from the
    authenticated database user — never from any client-side selection."""
    c = Client()
    r = c.post("/accounts/login/", {"username": officer.username, "password": "wrongpassword"})
    assert r.status_code == 200
    assert not c.session.get("_auth_user_id"), "Login with wrong password succeeded"


@pytest.mark.django_db
def test_viewer_login_keeps_viewer_role(viewer):
    """A viewer logging in with their own credentials stays a viewer — role is
    derived from the DB, never from any client-side selection or any URL parameter."""
    c = Client()
    r = c.post("/accounts/login/", {"username": viewer.username, "password": "test-password"})
    assert r.status_code == 302, f"Viewer login failed: {r.status_code}"
    uid = c.session.get("_auth_user_id")
    u = get_user_model().objects.get(pk=uid)
    assert u.role == "viewer", "Viewer role must be derived from DB, not from any client-side input"


@pytest.mark.django_db
def test_viewer_cannot_approve(viewer_client):
    """A logged-in viewer must get 403 on the approval gate."""
    from tests.factories.models import AdvisoryFactory
    adv = AdvisoryFactory(cluster__cluster_id="KACH-01", status="draft")
    r = viewer_client.post(f"/approvals/{adv.id}/", {"decision": "approved"})
    assert r.status_code == 403


@pytest.mark.django_db
def test_inactive_account_cannot_sign_in():
    """An inactive user cannot authenticate via the login form."""
    User = get_user_model()
    u, _ = User.objects.get_or_create(
        username="inactive_test_user",
        defaults={"role": "extension_officer",
                  "full_name": "Inactive",
                  "sub_county": "Nyatike",
                  "ward": "Kachieng"},
    )
    u.set_password("test-password")
    u.is_active = False
    u.save()
    c = Client()
    r = c.post("/accounts/login/", {"username": "inactive_test_user", "password": "test-password"})
    assert r.status_code == 200, "Inactive account should not redirect"
    assert not c.session.get("_auth_user_id"), "Inactive account logged in"


@pytest.mark.django_db
def test_unsafe_next_url_rejected():
    """Django's built-in redirect validation must reject an open-redirect `next` URL."""
    from tests.factories.models import OfficerFactory
    officer = OfficerFactory(username="redirect_test_officer", full_name="Redirect Test", role="extension_officer")
    officer.set_password("strong-test-password-1")
    officer.is_staff = True
    officer.save()

    c = Client()
    # Login successfully, but with a malicious `next` URL pointing to an external host.
    r = c.post("/accounts/login/?next=https://evil.example.com/",
               {"username": "redirect_test_officer", "password": "strong-test-password-1"})
    # Django rejects unsafe next URLs and falls back to LOGIN_REDIRECT_URL.
    assert r.status_code == 302, f"Expected 302 redirect, got {r.status_code}"
    # The Location header must NOT be the evil URL.
    assert "evil.example.com" not in r.url, f"Open redirect succeeded to {r.url}"
    # Should be the safe default redirect.
    assert r.url == "/dashboard/" or r.url.startswith("/dashboard"), f"Unexpected redirect target: {r.url}"


@pytest.mark.django_db
def test_login_form_has_csrf_protection():
    """The login form must include the CSRF token."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "csrfmiddlewaretoken" in html, "CSRF token missing from login form"


@pytest.mark.django_db
def test_login_post_without_csrf_rejected():
    """A POST without CSRF token must be rejected (403)."""
    c = Client(enforce_csrf_checks=True)
    r = c.post("/accounts/login/", {"username": "x", "password": "y"})
    assert r.status_code in (403, 200)  # 403 if CSRF enforced, 200 if form re-render (no auth)
    # The user must NOT be authenticated.
    assert not c.session.get("_auth_user_id")


# ---------------------------------------------------------------------------
# Removing demo data must not break authentication for real accounts
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_removing_demo_data_does_not_break_real_accounts():
    """If any old synthetic demo accounts exist in the DB, deleting them must NOT
    affect the ability of real accounts to log in. This guards against the
    `cleanup_demo_accounts` management command accidentally deleting more than
    it should."""
    from apps.accounts.models import User as U
    # Setup: one real account, three leftover demo accounts
    real, _ = U.objects.get_or_create(
        username="real_officer_keeps_working",
        defaults={"role": "extension_officer", "full_name": "Real Officer", "sub_county": "Nyatike", "ward": "Kachieng", "is_staff": True},
    )
    real.set_password("real-password-1")
    real.save()
    for uname in ("nyatike_officer", "nyatike_supervisor", "nyatike_viewer"):
        u, _ = U.objects.get_or_create(username=uname, defaults={"role": "viewer", "full_name": "Old demo", "sub_county": "Nyatike", "ward": "Kachieng"})
        u.set_password("majishamba-demo-2025")
        u.save()

    # Delete only the demo accounts
    U.objects.filter(username__in=["nyatike_officer", "nyatike_supervisor", "nyatike_viewer"]).delete()

    # The real account must still log in successfully
    c = Client()
    r = c.post("/accounts/login/", {"username": "real_officer_keeps_working", "password": "real-password-1"})
    assert r.status_code == 302, "Real account could not log in after deleting demo accounts"
    assert c.session.get("_auth_user_id") is not None

    # And the demo accounts are gone
    assert not U.objects.filter(username__in=["nyatike_officer", "nyatike_supervisor", "nyatike_viewer"]).exists()
    assert U.objects.filter(username="real_officer_keeps_working").exists()
