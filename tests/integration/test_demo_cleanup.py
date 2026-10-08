"""Tests for the cleanup_demo_accounts management command and demo-data removal.

Covers the success criteria from the cleanup task:
  * Identify existing demo accounts (read-only by default)
  * Optionally deactivate or delete them after owner approval (--confirm)
  * Preserve audit history linked to those accounts
  * Removing demo data does not break authentication for real accounts
  * No demo account cards / usernames appear in login/register HTML
  * Auth pages use the auth base template (operational navbar absent)
"""
from __future__ import annotations

import io

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client


User = get_user_model()


# ---------------------------------------------------------------------------
# cleanup_demo_accounts management command
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cleanup_command_lists_demo_accounts_by_default():
    """Without --confirm, the command only lists what it would do. No DB changes."""
    # Setup: create the three demo accounts
    for uname in ("nyatike_officer", "nyatike_supervisor", "nyatike_viewer"):
        u, _ = User.objects.get_or_create(
            username=uname,
            defaults={"role": "viewer", "full_name": "Old demo", "sub_county": "Nyatike", "ward": "Kachieng"},
        )
        u.set_password("x")
        u.save()

    out = io.StringIO()
    call_command("cleanup_demo_accounts", stdout=out, stderr=out)
    output = out.getvalue()
    assert "Found 3 matching account(s)" in output, output
    assert "DRY RUN" in output, "Default mode must be dry-run / read-only"
    # All three demo usernames should be visible in the listing
    for uname in ("nyatike_officer", "nyatike_supervisor", "nyatike_viewer"):
        assert uname in output

    # No DB changes were made
    assert User.objects.filter(username__in=["nyatike_officer", "nyatike_supervisor", "nyatike_viewer"]).count() == 3


@pytest.mark.django_db
def test_cleanup_command_no_matches():
    """When no demo accounts exist, the command reports success without doing anything."""
    # Ensure clean state
    User.objects.filter(username__in=["nyatike_officer", "nyatike_supervisor", "nyatike_viewer"]).delete()
    out = io.StringIO()
    call_command("cleanup_demo_accounts", stdout=out)
    output = out.getvalue()
    assert "No matching demo accounts found" in output


@pytest.mark.django_db
def test_cleanup_command_deactivates_with_confirm():
    """--confirm (without --delete) deactivates the demo accounts. Reversible."""
    for uname in ("nyatike_officer", "nyatike_supervisor", "nyatike_viewer"):
        u, _ = User.objects.get_or_create(
            username=uname,
            defaults={"role": "viewer", "full_name": "Old demo", "sub_county": "Nyatike", "ward": "Kachieng", "is_active": True},
        )
        u.set_password("x")
        u.save()
    out = io.StringIO()
    call_command("cleanup_demo_accounts", "--confirm", stdout=out)
    output = out.getvalue()
    assert "DEACTIVATED" in output
    assert "Done. 3 user(s) deactivated" in output
    # All three are now inactive
    for uname in ("nyatike_officer", "nyatike_supervisor", "nyatike_viewer"):
        u = User.objects.get(username=uname)
        assert u.is_active is False, f"{uname} should be deactivated"


@pytest.mark.django_db
def test_cleanup_command_delete_preserves_audit_history():
    """--confirm --delete hard-deletes the user but preserves audit rows (FK is SET_NULL)."""
    from apps.audit.models import AuditEvent

    # Create the demo officer + an audit event they triggered
    u, _ = User.objects.get_or_create(
        username="nyatike_officer",
        defaults={"role": "extension_officer", "full_name": "Old demo officer", "sub_county": "Nyatike", "ward": "Kachieng"},
    )
    AuditEvent.objects.create(actor=u, action="account:login")
    AuditEvent.objects.create(actor=u, action="advisory:approve")
    pre_count = AuditEvent.objects.filter(actor=u).count()
    assert pre_count == 2

    out = io.StringIO()
    call_command("cleanup_demo_accounts", "--confirm", "--delete", stdout=out)
    output = out.getvalue()
    assert "DELETED" in output
    assert "audit rows preserved" in output

    # User is gone
    assert not User.objects.filter(username="nyatike_officer").exists()
    # But the two audit events still exist — with NULL actor
    events = AuditEvent.objects.filter(action__in=["account:login", "advisory:approve"])
    assert events.count() == 2, "Audit events should still exist (preserved)"
    for e in events:
        assert e.actor is None, "Audit event actor should be NULL after user deleted (FK is SET_NULL)"


@pytest.mark.django_db
def test_cleanup_command_refuses_both_dry_run_and_confirm():
    """--dry-run and --confirm together must raise an error."""
    with pytest.raises(CommandError):
        call_command("cleanup_demo_accounts", "--dry-run", "--confirm")


@pytest.mark.django_db
def test_cleanup_command_refuses_delete_without_confirm():
    """--delete without --confirm must raise an error (no accidental deletes)."""
    User.objects.create(username="nyatike_officer", role="viewer", is_active=True)
    with pytest.raises(CommandError):
        call_command("cleanup_demo_accounts", "--delete")


@pytest.mark.django_db
def test_cleanup_command_only_targets_specified_usernames():
    """--usernames lets the operator target a custom list, but never anything else."""
    real_officer = User.objects.create(username="real_officer", role="extension_officer", is_active=True)
    leftover = User.objects.create(username="nyatike_officer", role="viewer", is_active=True)

    out = io.StringIO()
    call_command("cleanup_demo_accounts", "--usernames", "nyatike_officer", "--confirm", stdout=out)
    output = out.getvalue()
    assert "Done. 1 user(s) deactivated" in output

    leftover.refresh_from_db()
    real_officer.refresh_from_db()
    assert leftover.is_active is False, "The targeted demo account should be deactivated"
    assert real_officer.is_active is True, "The real officer should be untouched"


@pytest.mark.django_db
def test_cleanup_command_preserves_real_accounts():
    """The cleanup command must never deactivate or delete accounts that don't match."""
    real_officer = User.objects.create(username="real_officer", role="extension_officer", is_active=True)
    real_viewer = User.objects.create(username="real_viewer", role="viewer", is_active=True)
    User.objects.create(username="nyatike_officer", role="viewer", is_active=True)

    out = io.StringIO()
    call_command("cleanup_demo_accounts", "--confirm", stdout=out)

    real_officer.refresh_from_db()
    real_viewer.refresh_from_db()
    assert real_officer.is_active is True, "Real officer should not be touched"
    assert real_viewer.is_active is True, "Real viewer should not be touched"


@pytest.mark.django_db
def test_cleanup_command_include_pattern_matches_demo_flavoured_names():
    """--include-pattern also targets accounts matching nyatike_*, *demo*, *synthetic*."""
    User.objects.create(username="nyatike_officer", role="viewer", is_active=True)
    User.objects.create(username="demo_account_2", role="viewer", is_active=True)
    User.objects.create(username="synthetic_tester", role="viewer", is_active=True)
    User.objects.create(username="real_officer", role="extension_officer", is_active=True)

    out = io.StringIO()
    call_command("cleanup_demo_accounts", "--include-pattern", stdout=out)
    output = out.getvalue()
    # nyatike_officer (default), demo_account_2, synthetic_tester match the pattern
    # real_officer does NOT match
    assert "Found 3 matching account(s)" in output, output
    assert "nyatike_officer" in output
    assert "demo_account_2" in output
    assert "synthetic_tester" in output
    assert "real_officer" not in output


# ---------------------------------------------------------------------------
# Removing demo data does not break authentication for real accounts
# (covers the explicit success criterion in the task spec)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_removing_demo_data_does_not_break_authentication_for_real_accounts():
    """The full lifecycle: a real account is created and logged into, demo accounts
    are deleted via the cleanup command, and the real account still logs in fine."""
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

    # Delete the demo accounts via the cleanup command
    out = io.StringIO()
    call_command("cleanup_demo_accounts", "--confirm", "--delete", stdout=out)
    assert "Done" in out.getvalue()

    # The real account must still log in successfully
    c = Client()
    r = c.post("/accounts/login/", {"username": "real_officer_keeps_working", "password": "real-password-1"})
    assert r.status_code == 302, "Real account could not log in after deleting demo accounts"
    assert c.session.get("_auth_user_id") is not None

    # Demo accounts are gone
    assert not U.objects.filter(username__in=["nyatike_officer", "nyatike_supervisor", "nyatike_viewer"]).exists()
    # Real account is still present and active
    assert U.objects.filter(username="real_officer_keeps_working", is_active=True).exists()


# ---------------------------------------------------------------------------
# Auth pages use the auth base template (no operational navbar)
# (covers the explicit success criterion in the task spec)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auth_pages_use_auth_base_no_app_navbar():
    """Auth pages must use base_auth.html — no application navbar items, no
    htmx/maplibre-gl assets that are only loaded by base.html."""
    c = Client()
    for url in ["/accounts/login/", "/accounts/register/", "/accounts/registration/pending/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        # Operational nav links must NOT appear on auth pages
        assert "Dashboard" not in html, f"App nav link 'Dashboard' leaked onto {url}"
        assert "Advisories" not in html, f"App nav link 'Advisories' leaked onto {url}"
        assert "Tasks" not in html, f"App nav link 'Tasks' leaked onto {url}"
        assert "Audit" not in html, f"App nav link 'Audit' leaked onto {url}"
        # htmx and maplibre-gl are loaded only by base.html — their presence
        # indicates auth pages are using the wrong base template.
        assert "htmx.org" not in html, f"htmx loaded on auth page {url} — wrong base template"
        assert "maplibre-gl" not in html, f"maplibre-gl loaded on auth page {url} — wrong base template"


@pytest.mark.django_db
def test_demo_usernames_do_not_appear_in_auth_page_source():
    """No demo username or demo password hint may appear anywhere in the rendered
    HTML of the login, register, or registration_pending pages — including comments,
    data attributes, and JS."""
    c = Client()
    banned = [
        "nyatike_officer",
        "nyatike_supervisor",
        "nyatike_viewer",
        "majishamba-demo-2025",
        "majishamba-demo",
        "Choose a demo account",
        "Synthetic demo account",
        "Demo mode is ON",
        "demo account selector",
        "DEMO_MODE",
    ]
    for url in ["/accounts/login/", "/accounts/register/", "/accounts/registration/pending/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        for needle in banned:
            assert needle not in html, f"Banned reference {needle!r} found on {url}"


@pytest.mark.django_db
def test_login_card_has_no_old_taglines():
    """The login card must NOT contain the old taglines."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "Climate-smart advisories. Extension officers decide." not in html
    assert "Access agricultural advisories, field tasks and evidence review" not in html


@pytest.mark.django_db
def test_login_card_is_minimal():
    """The login card must have only: title 'Sign in', username field, password field
    with show/hide toggle, 'Sign in' button, and 'Need an account? Create one' link.
    No 'Forgot password?' (recovery not implemented)."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    # Required elements
    assert "Sign in" in html
    assert 'id="id_username"' in html
    assert 'id="id_password"' in html
    assert "Show password" in html  # aria-label on the toggle button
    assert "Sign in" in html  # button text
    assert "Need an account?" in html
    assert "Create one" in html
    # 'Forgot password?' must NOT appear because password recovery is NOT implemented
    assert "Forgot password" not in html, "Forgot-password link should not appear (no recovery implemented)"
    assert "forgot" not in html.lower(), "Forgot-password link should not appear (no recovery implemented)"
