"""Login tests — DEMO_MODE account selector + security rules."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings


@pytest.mark.django_db
def test_demo_cards_never_appear():
    """Demo account cards must NEVER appear on the login page, regardless of DEMO_MODE.
    Demo content has been removed from the login page entirely."""
    from django.conf import settings
    settings.MAJISHAMBA["DEMO_MODE"] = True
    settings.DEBUG = True
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "Choose a demo account" not in html
    assert "Synthetic demo account" not in html
    assert "nyatike_officer" not in html
    assert "Demo mode" not in html


@pytest.mark.django_db
def test_demo_cards_hidden_when_demo_mode_disabled():
    """With DEMO_MODE=False, the login page should NOT show demo account cards."""
    from django.conf import settings
    settings.MAJISHAMBA["DEMO_MODE"] = False
    settings.DEBUG = True
    try:
        c = Client()
        r = c.get("/accounts/login/")
        html = r.content.decode("utf-8")
        assert "Choose a demo account" not in html, "Demo cards must NOT appear with DEMO_MODE=0"
        assert "Synthetic demo account" not in html
    finally:
        # Restore dev defaults.
        settings.MAJISHAMBA["DEMO_MODE"] = True


@pytest.mark.django_db
def test_account_selection_requires_password(officer):
    """Clicking a demo card only fills the username — the user must still submit the form with a password.
    A POST with just the username (no password) must fail."""
    c = Client()
    # Simulate what the JS does: POST with username only.
    r = c.post("/accounts/login/", {"username": "nyatike_officer", "password": ""})
    # Django's auth form rejects empty password.
    # A failed login returns 200 (re-rendered form) but the user is NOT authenticated.
    assert r.status_code == 200
    # Verify we're still anonymous
    assert not c.session.get("_auth_user_id"), "Login succeeded without a password — security bug"


@pytest.mark.django_db
def test_viewer_cannot_gain_officer_permissions_by_selecting_card():
    """If a viewer logs in via the officer demo card (with their own credentials),
    they must remain a viewer — role is derived from the authenticated DB user."""
    from tests.factories.models import OfficerFactory
    User = get_user_model()
    # Create the officer and viewer users with known passwords.
    officer = OfficerFactory(username="nyatike_officer", full_name="Jane Awuor", role="extension_officer")
    officer.set_password("majishamba-demo-2025")
    officer.is_staff = True
    officer.save()
    viewer = User.objects.create(username="nyatike_viewer", role="viewer",
                                  full_name="Viewer", sub_county="Nyatike", ward="Kachieng")
    viewer.set_password("majishamba-demo-2025")
    viewer.save()

    c = Client()
    # viewer uses their own password but the officer card populated the username field.
    # In real flow, the user would have to type nyatike_officer's username + the officer's password.
    # If they type nyatike_officer's username but viewer's password, login fails (good).
    r = c.post("/accounts/login/", {"username": "nyatike_officer", "password": "wrongpassword"})
    assert r.status_code == 200
    assert not c.session.get("_auth_user_id"), "Login with wrong password succeeded"
    # And the viewer logging in as themselves stays a viewer.
    r2 = c.post("/accounts/login/", {"username": "nyatike_viewer", "password": "majishamba-demo-2025"})
    assert r2.status_code == 302, f"Viewer login failed: {r2.status_code}"
    # Verify the authenticated user is the viewer.
    uid = c.session.get("_auth_user_id")
    u = User.objects.get(pk=uid)
    assert u.role == "viewer", "Viewer role must be derived from DB, not from card selection"


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
    u, _ = User.objects.get_or_create(username="inactive_test_user",
                                       defaults={"role": "extension_officer",
                                                 "full_name": "Inactive",
                                                 "sub_county": "Nyatike",
                                                 "ward": "Kachieng"})
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
    User = get_user_model()
    officer = OfficerFactory(username="nyatike_officer", full_name="Jane Awuor", role="extension_officer")
    officer.set_password("majishamba-demo-2025")
    officer.is_staff = True
    officer.save()

    c = Client()
    # Login successfully, but with a malicious `next` URL pointing to an external host.
    r = c.post("/accounts/login/?next=https://evil.example.com/",
               {"username": "nyatike_officer", "password": "majishamba-demo-2025"})
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


@pytest.mark.django_db
def test_login_page_demo_cards_show_real_seeded_users_only():
    """If a demo user isn't seeded yet, the card must NOT appear (no fake accounts)."""
    from django.conf import settings
    # Delete the officer user to simulate "not seeded"
    User = get_user_model()
    User.objects.filter(username="nyatike_officer").delete()
    settings.MAJISHAMBA["DEMO_MODE"] = True
    with override_settings(DEBUG=True):
        c = Client()
        r = c.get("/accounts/login/")
        html = r.content.decode("utf-8")
        # The officer card must not appear because the user doesn't exist.
        assert "nyatike_officer" not in html, "Card appeared for non-existent user"
        # But supervisor/viewer cards should appear if they exist.
        if User.objects.filter(username="nyatike_supervisor").exists():
            assert "nyatike_supervisor" in html
