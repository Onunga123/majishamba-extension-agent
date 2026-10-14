"""Phase A regression tests — secure authentication and account approval.

Tests that pending accounts cannot log in, receive the correct message,
that approved accounts can log in, that rejected/suspended accounts are
blocked, that registration creates inactive pending accounts, that
approval reactivates accounts, and that existing sessions are invalidated
after deactivation.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()


# ---------------------------------------------------------------------------
# 1. Registration creates an inactive pending account
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_registration_creates_inactive_pending_account():
    """Registration must set both approval_status=PENDING and is_active=False."""
    c = Client()
    r = c.post("/accounts/register/", {
        "username": "phase_a_pending",
        "full_name": "Phase A Pending",
        "email": "",
        "requested_role": "viewer",
        "organization": "",
        "sub_county": "Nyatike",
        "ward": "Kachieng",
        "password1": "strong-password-1",
        "password2": "strong-password-1",
    })
    assert r.status_code == 302
    user = User.objects.get(username="phase_a_pending")
    assert user.approval_status == "pending"
    assert user.is_active is False, "Pending account must have is_active=False"


# ---------------------------------------------------------------------------
# 2. Pending accounts cannot log in
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_pending_user_cannot_login():
    """A pending user with valid credentials must NOT be able to log in."""
    user = User.objects.create(
        username="pending_login_test",
        full_name="Pending Login",
        role="viewer",
        approval_status="pending",
        is_active=False,
    )
    user.set_password("valid-password-1")
    user.save()

    c = Client()
    r = c.post("/accounts/login/", {"username": "pending_login_test", "password": "valid-password-1"})
    assert r.status_code == 200, "Pending user should NOT be redirected (login failed)"
    assert not c.session.get("_auth_user_id"), "Pending user must not have an authenticated session"


# ---------------------------------------------------------------------------
# 3. Pending users with valid credentials receive the correct message
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_pending_user_with_valid_credentials_shows_awaiting_approval_message():
    """A pending user who enters valid credentials should see the 'awaiting
    administrator approval' message, not a generic 'check your credentials' error.
    """
    user = User.objects.create(
        username="pending_message_test",
        full_name="Pending Message",
        role="viewer",
        approval_status="pending",
        is_active=False,
    )
    user.set_password("correct-password-1")
    user.save()

    c = Client()
    r = c.post("/accounts/login/", {"username": "pending_message_test", "password": "correct-password-1"})
    html = r.content.decode("utf-8")
    assert "awaiting administrator approval" in html.lower(), (
        "Pending user with valid credentials must see 'awaiting administrator approval' message"
    )
    assert "You can sign in once your account has been approved" in html


# ---------------------------------------------------------------------------
# 4. Invalid credentials receive a generic error
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_invalid_credentials_receive_generic_error(officer):
    """A wrong password must show a generic error, not disclose account existence."""
    c = Client()
    r = c.post("/accounts/login/", {"username": officer.username, "password": "wrong-password-xyz"})
    html = r.content.decode("utf-8")
    assert r.status_code == 200
    assert not c.session.get("_auth_user_id")
    assert "Please check your username and password" in html
    assert "awaiting administrator approval" not in html.lower()


@pytest.mark.django_db
def test_nonexistent_user_receives_generic_error():
    """A login attempt with a username that doesn't exist must NOT reveal
    that the username is unknown.
    """
    c = Client()
    r = c.post("/accounts/login/", {"username": "does_not_exist_user", "password": "any-password-1"})
    html = r.content.decode("utf-8")
    assert r.status_code == 200
    assert "Please check your username and password" in html
    assert "awaiting administrator approval" not in html.lower()


# ---------------------------------------------------------------------------
# 5. Approved accounts can log in
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_approved_user_can_login(officer):
    """An approved, active user must be able to log in."""
    c = Client()
    r = c.post("/accounts/login/", {"username": officer.username, "password": "test-password"})
    assert r.status_code == 302
    assert c.session.get("_auth_user_id") is not None


# ---------------------------------------------------------------------------
# 6. Rejected accounts cannot log in
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_rejected_user_cannot_login():
    """A rejected user (is_active=False) must not be able to log in."""
    user = User.objects.create(
        username="rejected_login_test",
        full_name="Rejected Login",
        role="viewer",
        approval_status="rejected",
        is_active=False,
    )
    user.set_password("rejected-password-1")
    user.save()

    c = Client()
    r = c.post("/accounts/login/", {"username": "rejected_login_test", "password": "rejected-password-1"})
    assert r.status_code == 200
    assert not c.session.get("_auth_user_id")
    # Must NOT show "awaiting approval" — that's for pending only
    html = r.content.decode("utf-8")
    assert "awaiting administrator approval" not in html.lower()


# ---------------------------------------------------------------------------
# 7. Suspended accounts cannot log in
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_suspended_user_cannot_login():
    """A suspended user (is_active=False) must not be able to log in."""
    user = User.objects.create(
        username="suspended_login_test",
        full_name="Suspended Login",
        role="viewer",
        approval_status="suspended",
        is_active=False,
    )
    user.set_password("suspended-password-1")
    user.save()

    c = Client()
    r = c.post("/accounts/login/", {"username": "suspended_login_test", "password": "suspended-password-1"})
    assert r.status_code == 200
    assert not c.session.get("_auth_user_id")


# ---------------------------------------------------------------------------
# 8. Approval reactivates the account
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_approval_reactivates_account(system_admin):
    """Approving a pending account must set is_active=True and approval_status=approved,
    so the user can then log in.
    """
    pending = User.objects.create(
        username="pending_approval_test",
        full_name="Pending Approval",
        role="viewer",
        requested_role="extension_officer",
        approval_status="pending",
        is_active=False,
    )
    pending.set_password("approval-password-1")
    pending.save()

    c = Client()
    c.force_login(system_admin)
    r = c.post(f"/accounts/review/{pending.id}/approve/", {"effective_role": "extension_officer"})
    assert r.status_code == 302

    pending.refresh_from_db()
    assert pending.approval_status == "approved"
    assert pending.is_active is True
    assert pending.role == "extension_officer"

    # Now the user should be able to log in
    c2 = Client()
    r2 = c2.post("/accounts/login/", {"username": "pending_approval_test", "password": "approval-password-1"})
    assert r2.status_code == 302, "Approved user must be able to log in"
    assert c2.session.get("_auth_user_id") is not None


# ---------------------------------------------------------------------------
# 9. Existing sessions are invalidated after deactivation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_session_invalidated_after_deactivation(officer):
    """If an admin sets is_active=False on an approved user who has an
    active session, the next authenticated request must redirect to login.

    Django's ModelBackend.get_user() already handles is_active=False by
    returning None (making request.user = AnonymousUser). LoginRequiredMixin
    then redirects to /accounts/login/. Our middleware adds the
    approval_status check on top.
    """
    c = Client()
    c.force_login(officer)
    # Verify the session is active
    assert c.session.get("_auth_user_id") is not None

    # Deactivate the user
    officer.is_active = False
    officer.save()

    # The next request should redirect to login (via Django's built-in
    # is_active check, which makes request.user = AnonymousUser, then
    # LoginRequiredMixin redirects to /accounts/login/)
    r = c.get("/dashboard/")
    assert r.status_code in {302, 301}, "Deactivated user should be redirected to login"
    assert "/accounts/login/" in r["Location"]


@pytest.mark.django_db
def test_session_invalidated_after_rejection(officer):
    """If an admin rejects an account (approval_status=rejected, is_active=False),
    the user's existing session is invalidated via Django's is_active check.
    """
    c = Client()
    c.force_login(officer)
    assert c.session.get("_auth_user_id") is not None

    officer.approval_status = "rejected"
    officer.is_active = False
    officer.save()

    r = c.get("/dashboard/")
    assert r.status_code in {302, 301}
    assert "/accounts/login/" in r["Location"]


@pytest.mark.django_db
def test_session_invalidated_after_approval_status_change_only(officer):
    """If an admin changes approval_status without setting is_active=False
    (edge case), the middleware catches it and flushes the session.
    """
    c = Client()
    c.force_login(officer)
    assert c.session.get("_auth_user_id") is not None

    # Change only approval_status — keep is_active=True
    officer.approval_status = "pending"
    officer.is_active = True  # explicitly keep active
    officer.save()

    r = c.get("/dashboard/")
    assert r.status_code in {302, 301}, (
        "User with approval_status != approved must be redirected by the middleware"
    )
    assert "/accounts/login/" in r["Location"]


@pytest.mark.django_db
def test_session_not_invalidated_for_approved_user(officer):
    """An approved, active user's session should NOT be invalidated."""
    c = Client()
    c.force_login(officer)
    r = c.get("/dashboard/")
    assert r.status_code == 200, "Approved user should still be able to access dashboard"


# ---------------------------------------------------------------------------
# 10. Anonymous registration and login continue to work
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_anonymous_can_access_login_page():
    """The login page must remain accessible to anonymous users."""
    c = Client()
    r = c.get("/accounts/login/")
    assert r.status_code == 200
    assert "Sign in" in r.content.decode("utf-8")


@pytest.mark.django_db
def test_anonymous_can_access_register_page():
    """The registration page must remain accessible to anonymous users."""
    c = Client()
    r = c.get("/accounts/register/")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# 11. CSRF protection preserved
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_post_without_csrf_rejected():
    """Login POST without CSRF token must be rejected."""
    c = Client(enforce_csrf_checks=True)
    r = c.post("/accounts/login/", {"username": "someuser", "password": "somepassword"})
    assert r.status_code == 403


@pytest.mark.django_db
def test_logout_requires_post():
    """Logout via GET should not work (must be POST for CSRF safety)."""
    c = Client(enforce_csrf_checks=True)
    r = c.get("/accounts/logout/")
    assert r.status_code == 405


# ---------------------------------------------------------------------------
# 12. Account permissions remain intact
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_viewer_cannot_access_account_review(viewer_client):
    """A viewer must still get 403 on the account review page."""
    r = viewer_client.get("/accounts/review/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_supervisor_cannot_review_accounts(supervisor):
    """Supervisors must still not be able to access account review."""
    c = Client()
    c.force_login(supervisor)
    assert c.get("/accounts/review/").status_code == 403


@pytest.mark.django_db
def test_system_admin_can_still_access_review(system_admin):
    """System admins must still be able to access the account review page."""
    c = Client()
    c.force_login(system_admin)
    r = c.get("/accounts/review/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_user_cannot_approve_own_account(system_admin):
    """A user must not be able to approve their own account."""
    c = Client()
    c.force_login(system_admin)
    r = c.post(f"/accounts/review/{system_admin.id}/approve/", {"effective_role": "system_admin"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 13. Admin access is NOT exempt from session revalidation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_deactivated_user_cannot_access_admin(officer):
    """A deactivated user (is_active=False) must NOT be able to access /admin/
    through an existing session. Django's ModelBackend.get_user() returns None
    for inactive users, making request.user = AnonymousUser. The admin site
    then redirects to /admin/login/. The key security guarantee: the user
    cannot see any admin content.
    """
    c = Client()
    c.force_login(officer)
    assert c.session.get("_auth_user_id") is not None

    # Deactivate the user
    officer.is_active = False
    officer.save()

    # The admin page must redirect (either to /accounts/login/ via our
    # middleware or /admin/login/ via Django's admin). Either way, the
    # user cannot access admin content.
    r = c.get("/admin/")
    assert r.status_code in {302, 301}, (
        "Deactivated user accessing /admin/ must be redirected, "
        "not allowed to view admin content."
    )
    # Must redirect to a login page, NOT show admin content
    location = r["Location"]
    assert "/login/" in location, f"Expected redirect to a login page, got {location}"


@pytest.mark.django_db
def test_deactivated_user_cannot_access_admin_subpath(officer):
    """A deactivated user must NOT be able to access any /admin/ subpath."""
    c = Client()
    c.force_login(officer)

    officer.is_active = False
    officer.save()

    r = c.get("/admin/auth/user/")
    assert r.status_code in {302, 301}
    location = r["Location"]
    assert "/login/" in location, f"Expected redirect to a login page, got {location}"


@pytest.mark.django_db
def test_approval_status_change_blocks_admin_access(officer):
    """If an admin changes approval_status to pending (without setting
    is_active=False), the middleware must block access to /admin/.
    Django's admin checks is_active (which is still True), but our
    middleware checks approval_status and flushes the session.
    """
    c = Client()
    c.force_login(officer)
    officer.is_staff = True
    officer.save()

    # Change only approval_status — keep is_active=True
    officer.approval_status = "pending"
    officer.is_active = True
    officer.save()

    r = c.get("/admin/")
    # Our middleware should fire (is_active=True but approval_status != approved)
    assert r.status_code in {302, 301}, (
        "User with non-approved status must be redirected from /admin/"
    )
    assert "/accounts/login/" in r["Location"], (
        "Middleware should redirect to /accounts/login/ for non-approved users"
    )


@pytest.mark.django_db
def test_approved_user_can_still_access_admin_if_staff(officer):
    """An approved, active, is_staff user must still be able to access /admin/.
    The middleware must NOT block legitimate admin access.
    """
    officer.is_staff = True
    officer.save()

    c = Client()
    c.force_login(officer)
    # Django admin will redirect to its own login page if the user is
    # authenticated but not is_staff, or will show the admin index if is_staff.
    # The key assertion is that the middleware does NOT redirect to /accounts/login/.
    r = c.get("/admin/")
    # If is_staff=True, Django admin shows the index (200) or its own login (302 to /admin/login/).
    # It should NOT be a 302 to /accounts/login/ — that would mean the middleware kicked in.
    if r.status_code == 302:
        assert "/accounts/login/" not in r["Location"], (
            "Approved, active, is_staff user must not be kicked out of /admin/ by the middleware"
        )


# ---------------------------------------------------------------------------
# 14. Data migration: existing pending accounts are deactivated
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_migration_deactivates_existing_pending_accounts():
    """The data migration must deactivate pending accounts that have
    is_active=True (the pre-Phase-A default).
    """
    from apps.accounts.models import User

    user = User.objects.create(
        username="pre_phase_a_pending",
        full_name="Pre Phase A",
        role="viewer",
        approval_status="pending",
        is_active=True,
    )

    import importlib
    _migration = importlib.import_module(
        "apps.accounts.migrations.0005_deactivate_existing_pending_accounts"
    )
    deactivate_pending_accounts = _migration.deactivate_pending_accounts
    from django.apps import apps as django_apps
    deactivate_pending_accounts(django_apps, None)

    user.refresh_from_db()
    assert user.is_active is False, (
        "Migration must set is_active=False on pending accounts with is_active=True"
    )
    assert user.approval_status == "pending", "Migration must not change approval_status"


@pytest.mark.django_db
def test_migration_does_not_touch_approved_accounts():
    """The data migration must NOT touch approved accounts."""
    from apps.accounts.models import User

    user = User.objects.create(
        username="approved_not_affected",
        full_name="Approved User",
        role="viewer",
        approval_status="approved",
        is_active=True,
    )

    import importlib
    _migration = importlib.import_module(
        "apps.accounts.migrations.0005_deactivate_existing_pending_accounts"
    )
    deactivate_pending_accounts = _migration.deactivate_pending_accounts
    from django.apps import apps as django_apps
    deactivate_pending_accounts(django_apps, None)

    user.refresh_from_db()
    assert user.is_active is True, "Migration must not deactivate approved accounts"
    assert user.approval_status == "approved"


@pytest.mark.django_db
def test_migration_does_not_touch_rejected_accounts():
    """The data migration must NOT touch rejected accounts (they should
    already have is_active=False from the rejection flow).
    """
    from apps.accounts.models import User

    user = User.objects.create(
        username="rejected_not_affected",
        full_name="Rejected User",
        role="viewer",
        approval_status="rejected",
        is_active=False,
    )

    import importlib
    _migration = importlib.import_module(
        "apps.accounts.migrations.0005_deactivate_existing_pending_accounts"
    )
    deactivate_pending_accounts = _migration.deactivate_pending_accounts
    from django.apps import apps as django_apps
    deactivate_pending_accounts(django_apps, None)

    user.refresh_from_db()
    assert user.is_active is False
    assert user.approval_status == "rejected"


@pytest.mark.django_db
def test_migration_is_idempotent():
    """Running the migration twice must not cause errors or change
    already-deactivated accounts further.
    """
    from apps.accounts.models import User

    user = User.objects.create(
        username="idempotent_test",
        full_name="Idempotent",
        role="viewer",
        approval_status="pending",
        is_active=True,
    )

    import importlib
    _migration = importlib.import_module(
        "apps.accounts.migrations.0005_deactivate_existing_pending_accounts"
    )
    deactivate_pending_accounts = _migration.deactivate_pending_accounts
    from django.apps import apps as django_apps

    deactivate_pending_accounts(django_apps, None)
    deactivate_pending_accounts(django_apps, None)

    user.refresh_from_db()
    assert user.is_active is False
    assert user.approval_status == "pending"


@pytest.mark.django_db
def test_migration_is_irreversible():
    """The migration must be formally irreversible: the reverse callable must
    be None (omitted from RunPython), so Django raises IrreversibleError if
    anyone attempts to roll it back. This prevents accidental reactivation
    of unapproved pending accounts.
    """
    import importlib
    from django.db import migrations

    _migration = importlib.import_module(
        "apps.accounts.migrations.0005_deactivate_existing_pending_accounts"
    )

    migration = _migration.Migration
    assert len(migration.operations) == 1
    op = migration.operations[0]
    assert isinstance(op, migrations.RunPython)
    # The reverse callable must be None (omitted), NOT noop or a custom function.
    # When reverse_code is None, Django raises an IrreversibleError on rollback.
    assert op.reverse_code is None, (
        "Migration reverse must be None (irreversible), not noop or a reactivation function"
    )


@pytest.mark.django_db
def test_migration_rollback_raises_irreversible_error():
    """Attempting to reverse the migration via Django's migration machinery
    must raise an IrreversibleError. This is the concrete proof that
    rollback cannot reactivate unapproved accounts.

    Django's Migration.unapply() checks operation.reversible before
    calling database_backwards. RunPython.reversible returns False when
    reverse_code is None, causing Migration.unapply() to raise
    IrreversibleError. We verify both: the reversible property is False,
    and calling unapply raises IrreversibleError.
    """
    import importlib
    from django.apps import apps as django_apps

    _migration = importlib.import_module(
        "apps.accounts.migrations.0005_deactivate_existing_pending_accounts"
    )

    op = _migration.Migration.operations[0]
    assert op.reverse_code is None
    assert op.reversible is False, (
        "RunPython with no reverse_code must have reversible=False"
    )

    from django.db.migrations.exceptions import IrreversibleError
    from django.db.migrations.state import ProjectState

    # Build the migration instance and attempt to unapply it
    migration_instance = _migration.Migration("0005_deactivate_existing_pending_accounts", "accounts")
    from django.db import connection
    schema_editor = connection.schema_editor()
    project_state = ProjectState()

    with pytest.raises(IrreversibleError):
        migration_instance.unapply(project_state, schema_editor)


@pytest.mark.django_db
def test_migration_only_deactivates_pending_active_accounts():
    """The migration must change ONLY accounts with approval_status='pending'
    AND is_active=True. Approved, rejected, suspended, and already-inactive
    accounts must not be touched.
    """
    from apps.accounts.models import User

    # Create accounts in every state
    pending_active = User.objects.create(
        username="pending_active", full_name="Pending Active",
        role="viewer", approval_status="pending", is_active=True,
    )
    pending_inactive = User.objects.create(
        username="pending_inactive", full_name="Pending Inactive",
        role="viewer", approval_status="pending", is_active=False,
    )
    approved_active = User.objects.create(
        username="approved_active", full_name="Approved Active",
        role="viewer", approval_status="approved", is_active=True,
    )
    rejected_inactive = User.objects.create(
        username="rejected_inactive", full_name="Rejected Inactive",
        role="viewer", approval_status="rejected", is_active=False,
    )
    suspended_active = User.objects.create(
        username="suspended_active", full_name="Suspended Active",
        role="viewer", approval_status="suspended", is_active=True,
    )

    import importlib
    _migration = importlib.import_module(
        "apps.accounts.migrations.0005_deactivate_existing_pending_accounts"
    )
    from django.apps import apps as django_apps
    _migration.deactivate_pending_accounts(django_apps, None)

    # Only pending+active should be changed
    pending_active.refresh_from_db()
    assert pending_active.is_active is False, "Pending+active must be deactivated"

    pending_inactive.refresh_from_db()
    assert pending_inactive.is_active is False, "Pending+inactive must remain inactive"

    approved_active.refresh_from_db()
    assert approved_active.is_active is True, "Approved+active must NOT be touched"

    rejected_inactive.refresh_from_db()
    assert rejected_inactive.is_active is False, "Rejected+inactive must NOT be touched"

    suspended_active.refresh_from_db()
    assert suspended_active.is_active is True, "Suspended+active must NOT be touched"
