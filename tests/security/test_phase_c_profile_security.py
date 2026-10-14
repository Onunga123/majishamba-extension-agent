"""Phase C regression tests — profile-editing authorization and account-change security.

These tests verify the approved Phase C scope:

1. ``/accounts/profile/`` is read-only and authenticated-only.
   - Anonymous users are redirected to /accounts/login/ (302).
   - POST / PUT / PATCH / DELETE requests receive HTTP 405.
   - The view only ever uses ``request.user`` (no URL parameter), so there is
     no way to view another user's profile through this endpoint.

2. Registration privilege-field tampering is blocked.
   - ``requested_role=system_admin`` is rejected by the ChoiceField.
   - ``approval_status=approved`` cannot bypass the PENDING default.
   - ``role=system_admin`` (or any value) cannot bypass the VIEWER default.

3. Direct POST authorization on account approve / reject endpoints.
   - Viewer, Extension Officer, and Supervisor POSTing to
     ``/accounts/review/<pk>/approve/`` or ``/accounts/review/<pk>/reject/``
     receive 403 and do not mutate the target account.
   - Anonymous POST is redirected to login (302).
   - System admin can still approve / reject (regression guard).

4. Cross-user protection: a system admin cannot approve their own account
   (already covered by test_auth.py::test_user_cannot_approve_own_account
   and test_pending_account_security.py::test_user_cannot_approve_own_account
   — not duplicated here).

Out of scope (not tested here):
- Password-change functionality (does not exist; deferred).
- Email notifications (not configured; deferred).
- Django admin privilege pathway (Phase A design decision; out of scope).
- ``AccountApproveView`` accepting ``effective_role=system_admin`` (intended
  admin capability; left unchanged per approval).
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()


# ---------------------------------------------------------------------------
# 1. /accounts/profile/ — authentication + method restrictions
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_profile_anonymous_redirected_to_login():
    """Anonymous GET to /accounts/profile/ must redirect to login (302), not 200."""
    c = Client()
    r = c.get("/accounts/profile/")
    assert r.status_code in {302, 301}, (
        f"Anonymous /accounts/profile/ should redirect to login, got {r.status_code}"
    )
    assert "/accounts/login/" in r["Location"], (
        f"Anonymous /accounts/profile/ should redirect to /accounts/login/, got {r['Location']}"
    )


@pytest.mark.django_db
def test_profile_officer_get_allowed(officer_client):
    """An authenticated officer can GET /accounts/profile/ and receive 200."""
    r = officer_client.get("/accounts/profile/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_profile_viewer_get_allowed(viewer_client):
    """An authenticated viewer can GET /accounts/profile/ and receive 200."""
    r = viewer_client.get("/accounts/profile/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_profile_supervisor_get_allowed(supervisor_client):
    """An authenticated supervisor can GET /accounts/profile/ and receive 200."""
    r = supervisor_client.get("/accounts/profile/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_profile_system_admin_get_allowed(system_admin_client):
    """An authenticated system admin can GET /accounts/profile/ and receive 200."""
    r = system_admin_client.get("/accounts/profile/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_profile_post_rejected_with_405(officer_client):
    """POST to /accounts/profile/ must return 405 (Method Not Allowed).

    The profile page is read-only; no mutation path exists.
    """
    r = officer_client.post("/accounts/profile/", {"full_name": "Hacker"})
    assert r.status_code == 405, (
        f"POST /accounts/profile/ should return 405, got {r.status_code}"
    )


@pytest.mark.django_db
def test_profile_put_rejected_with_405(officer_client):
    """PUT to /accounts/profile/ must return 405."""
    r = officer_client.put("/accounts/profile/")
    assert r.status_code == 405


@pytest.mark.django_db
def test_profile_patch_rejected_with_405(officer_client):
    """PATCH to /accounts/profile/ must return 405."""
    r = officer_client.patch("/accounts/profile/")
    assert r.status_code == 405


@pytest.mark.django_db
def test_profile_delete_rejected_with_405(officer_client):
    """DELETE to /accounts/profile/ must return 405."""
    r = officer_client.delete("/accounts/profile/")
    assert r.status_code == 405


@pytest.mark.django_db
def test_profile_post_does_not_mutate_user(officer_client, officer):
    """A POST attempt must not change any field on the authenticated user.

    This guards against a regression where the view is changed to accept POST
    without proper form handling — even if the response code changes, the user
    record must remain unchanged.
    """
    original_full_name = officer.full_name
    original_email = officer.email
    original_role = officer.role
    original_sub_county = officer.sub_county
    original_ward = officer.ward

    r = officer_client.post("/accounts/profile/", {
        "full_name": "Hacker Name",
        "email": "hacker@example.com",
        "role": "system_admin",
        "sub_county": "Nairobi",
        "ward": "Central",
        "is_staff": "true",
        "is_superuser": "true",
        "approval_status": "approved",
        "is_active": "true",
    })
    assert r.status_code == 405

    officer.refresh_from_db()
    assert officer.full_name == original_full_name
    assert officer.email == original_email
    assert officer.role == original_role
    assert officer.sub_county == original_sub_county
    assert officer.ward == original_ward
    assert officer.is_staff is True  # was True before (officer fixture sets it)
    assert officer.is_superuser is False
    assert officer.approval_status == "approved"
    assert officer.is_active is True


@pytest.mark.django_db
def test_profile_anonymous_post_redirected_to_login_not_405():
    """Anonymous POST to /accounts/profile/ must redirect to login (302),
    not 405. The auth guard runs before the method guard (decorator order:
    login_required is outermost, require_http_methods is innermost — but
    Django applies the outermost decorator first, so anonymous requests are
    caught by login_required before the method check).

    This documents the decorator ordering and guards against a regression
    where the order is swapped (which would leak the endpoint's existence
    to anonymous users via 405).
    """
    c = Client()
    r = c.post("/accounts/profile/")
    assert r.status_code in {302, 301}, (
        f"Anonymous POST /accounts/profile/ should redirect to login, got {r.status_code}"
    )
    assert "/accounts/login/" in r["Location"]


@pytest.mark.django_db
def test_profile_does_not_accept_url_parameter_for_other_user(officer_client, officer):
    """The profile view must only ever display request.user, never a URL
    parameter. There is no /accounts/profile/<pk>/ route (the URLconf only
    registers /accounts/profile/ with no capture group), so a request with
    a trailing ID must 404 — confirming cross-user access via URL is
    impossible.
    """
    # Create a second user
    other = User.objects.create(
        username="other_officer", full_name="Other Officer", role="extension_officer",
        approval_status="approved", is_active=True,
    )
    # The profile URL has no <pk> capture — any trailing path segment 404s
    r = officer_client.get(f"/accounts/profile/{other.id}/")
    assert r.status_code == 404, (
        f"GET /accounts/profile/<pk>/ should 404 (no such route), got {r.status_code}"
    )


# ---------------------------------------------------------------------------
# 2. Registration privilege-field tampering (regression guards)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_registration_cannot_request_system_admin_role():
    """A crafted POST with requested_role=system_admin must be rejected by
    the ChoiceField (which only lists extension_officer, supervisor, viewer).

    This is a regression guard: if the ChoiceField choices are ever expanded
    to include system_admin, this test will catch it.
    """
    c = Client()
    r = c.post("/accounts/register/", {
        "username": "phase_c_role_hacker",
        "full_name": "Role Hacker",
        "email": "",
        "requested_role": "system_admin",
        "organization": "",
        "sub_county": "Nyatike",
        "ward": "Kachieng",
        "password1": "hacker-password-1",
        "password2": "hacker-password-1",
    })
    # Form should be invalid (200) — requested_role=system_admin is not a valid choice
    assert r.status_code == 200, (
        f"Registration with requested_role=system_admin should fail at form validation, got {r.status_code}"
    )
    assert not User.objects.filter(username="phase_c_role_hacker").exists(), (
        "No user should be created when requested_role=system_admin is submitted"
    )


@pytest.mark.django_db
def test_registration_cannot_set_approval_status_to_approved():
    """A crafted POST with approval_status=approved must NOT bypass the
    PENDING default enforced by RegistrationForm.save().

    approval_status is not in RegistrationForm.Meta.fields, so Django's
    ModelForm ignores it. RegistrationForm.save() explicitly forces
    approval_status=PENDING. This test guards against a regression where
    the save() override is removed or Meta.fields is expanded.
    """
    c = Client()
    r = c.post("/accounts/register/", {
        "username": "phase_c_status_hacker",
        "full_name": "Status Hacker",
        "email": "",
        "requested_role": "viewer",
        "organization": "",
        "sub_county": "Nyatike",
        "ward": "Kachieng",
        "password1": "hacker-password-1",
        "password2": "hacker-password-1",
        "approval_status": "approved",
        "is_active": "true",
    })
    assert r.status_code == 302
    user = User.objects.get(username="phase_c_status_hacker")
    assert user.approval_status == "pending", (
        f"Registration must force approval_status=pending regardless of POST, got {user.approval_status}"
    )
    assert user.is_active is False, (
        "Registration must force is_active=False regardless of POST"
    )


@pytest.mark.django_db
def test_registration_cannot_set_role_directly():
    """A crafted POST with role=system_admin must NOT bypass the VIEWER
    default enforced by RegistrationForm.save().

    role is not in RegistrationForm.Meta.fields, so Django's ModelForm
    ignores it. RegistrationForm.save() explicitly forces role=VIEWER.
    This test guards against a regression where the save() override is
    removed or Meta.fields is expanded to include role.
    """
    c = Client()
    r = c.post("/accounts/register/", {
        "username": "phase_c_role_direct_hacker",
        "full_name": "Role Direct Hacker",
        "email": "",
        "requested_role": "viewer",
        "organization": "",
        "sub_county": "Nyatike",
        "ward": "Kachieng",
        "password1": "hacker-password-1",
        "password2": "hacker-password-1",
        "role": "system_admin",
    })
    assert r.status_code == 302
    user = User.objects.get(username="phase_c_role_direct_hacker")
    assert user.role == "viewer", (
        f"Registration must force role=viewer regardless of POST, got {user.role}"
    )


# ---------------------------------------------------------------------------
# 3. Direct POST authorization on account approve / reject endpoints
# ---------------------------------------------------------------------------
def _make_pending_user(username="phase_c_pending"):
    """Create a pending account for approve/reject tests."""
    return User.objects.create(
        username=username,
        full_name="Phase C Pending",
        role="viewer",
        requested_role="extension_officer",
        approval_status="pending",
        is_active=True,
    )


@pytest.mark.django_db
def test_viewer_cannot_post_approve(viewer_client):
    """A viewer POSTing to /accounts/review/<pk>/approve/ must receive 403
    and the target account must remain pending."""
    pending = _make_pending_user()
    r = viewer_client.post(
        f"/accounts/review/{pending.id}/approve/",
        {"effective_role": "extension_officer"},
    )
    assert r.status_code == 403, (
        f"Viewer should be denied approve POST, got {r.status_code}"
    )
    pending.refresh_from_db()
    assert pending.approval_status == "pending", (
        "Target account must remain pending after viewer approve attempt"
    )
    assert pending.role == "viewer"
    assert pending.is_active is True


@pytest.mark.django_db
def test_officer_cannot_post_approve(officer_client):
    """An Extension Officer POSTing to /accounts/review/<pk>/approve/ must
    receive 403 and the target account must remain pending."""
    pending = _make_pending_user()
    r = officer_client.post(
        f"/accounts/review/{pending.id}/approve/",
        {"effective_role": "extension_officer"},
    )
    assert r.status_code == 403
    pending.refresh_from_db()
    assert pending.approval_status == "pending"
    assert pending.role == "viewer"


@pytest.mark.django_db
def test_supervisor_cannot_post_approve(supervisor_client):
    """A Supervisor POSTing to /accounts/review/<pk>/approve/ must receive
    403 and the target account must remain pending."""
    pending = _make_pending_user()
    r = supervisor_client.post(
        f"/accounts/review/{pending.id}/approve/",
        {"effective_role": "extension_officer"},
    )
    assert r.status_code == 403
    pending.refresh_from_db()
    assert pending.approval_status == "pending"
    assert pending.role == "viewer"


@pytest.mark.django_db
def test_viewer_cannot_post_reject(viewer_client):
    """A viewer POSTing to /accounts/review/<pk>/reject/ must receive 403
    and the target account must remain pending."""
    pending = _make_pending_user()
    r = viewer_client.post(
        f"/accounts/review/{pending.id}/reject/",
        {"rejection_reason": "Attempted by viewer"},
    )
    assert r.status_code == 403
    pending.refresh_from_db()
    assert pending.approval_status == "pending"
    assert pending.is_active is True


@pytest.mark.django_db
def test_officer_cannot_post_reject(officer_client):
    """An Extension Officer POSTing to /accounts/review/<pk>/reject/ must
    receive 403 and the target account must remain pending."""
    pending = _make_pending_user()
    r = officer_client.post(
        f"/accounts/review/{pending.id}/reject/",
        {"rejection_reason": "Attempted by officer"},
    )
    assert r.status_code == 403
    pending.refresh_from_db()
    assert pending.approval_status == "pending"


@pytest.mark.django_db
def test_supervisor_cannot_post_reject(supervisor_client):
    """A Supervisor POSTing to /accounts/review/<pk>/reject/ must receive
    403 and the target account must remain pending."""
    pending = _make_pending_user()
    r = supervisor_client.post(
        f"/accounts/review/{pending.id}/reject/",
        {"rejection_reason": "Attempted by supervisor"},
    )
    assert r.status_code == 403
    pending.refresh_from_db()
    assert pending.approval_status == "pending"


@pytest.mark.django_db
def test_anonymous_approve_post_redirected_to_login():
    """Anonymous POST to /accounts/review/<pk>/approve/ must redirect to
    login (302), not 403 or 200."""
    pending = _make_pending_user()
    c = Client()
    r = c.post(f"/accounts/review/{pending.id}/approve/", {"effective_role": "viewer"})
    assert r.status_code in {302, 301}, (
        f"Anonymous approve POST should redirect to login, got {r.status_code}"
    )
    assert "/accounts/login/" in r["Location"]
    pending.refresh_from_db()
    assert pending.approval_status == "pending"


@pytest.mark.django_db
def test_anonymous_reject_post_redirected_to_login():
    """Anonymous POST to /accounts/review/<pk>/reject/ must redirect to
    login (302)."""
    pending = _make_pending_user()
    c = Client()
    r = c.post(f"/accounts/review/{pending.id}/reject/", {"rejection_reason": "anon"})
    assert r.status_code in {302, 301}
    assert "/accounts/login/" in r["Location"]
    pending.refresh_from_db()
    assert pending.approval_status == "pending"


@pytest.mark.django_db
def test_system_admin_approve_still_works(system_admin_client):
    """Regression guard: a system admin can still approve a pending account."""
    pending = _make_pending_user()
    r = system_admin_client.post(
        f"/accounts/review/{pending.id}/approve/",
        {"effective_role": "extension_officer"},
    )
    assert r.status_code == 302
    pending.refresh_from_db()
    assert pending.approval_status == "approved"
    assert pending.role == "extension_officer"


@pytest.mark.django_db
def test_system_admin_reject_still_works(system_admin_client):
    """Regression guard: a system admin can still reject a pending account."""
    pending = _make_pending_user()
    r = system_admin_client.post(
        f"/accounts/review/{pending.id}/reject/",
        {"rejection_reason": "Phase C test rejection"},
    )
    assert r.status_code == 302
    pending.refresh_from_db()
    assert pending.approval_status == "rejected"
    assert pending.is_active is False
    assert pending.rejection_reason == "Phase C test rejection"


# ---------------------------------------------------------------------------
# 4. Approve endpoint: cannot approve a non-pending account
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_system_admin_cannot_approve_already_approved_account(system_admin_client):
    """A system admin POSTing to /accounts/review/<pk>/approve/ for an
    already-approved account must NOT change its state. The view redirects
    with a warning (line 275-277), leaving the account unchanged.
    """
    already_approved = User.objects.create(
        username="phase_c_already_approved",
        full_name="Already Approved",
        role="viewer",
        requested_role="viewer",
        approval_status="approved",
        is_active=True,
    )
    r = system_admin_client.post(
        f"/accounts/review/{already_approved.id}/approve/",
        {"effective_role": "system_admin"},
    )
    # The view redirects to /accounts/review/ with a warning message
    assert r.status_code == 302
    already_approved.refresh_from_db()
    # The account must remain in its original state — the approve endpoint
    # does not promote an already-approved account.
    assert already_approved.approval_status == "approved"
    assert already_approved.role == "viewer", (
        "Approve endpoint must not change the role of an already-approved account"
    )


@pytest.mark.django_db
def test_system_admin_cannot_approve_nonexistent_account(system_admin_client):
    """A system admin POSTing to a non-existent account pk must get 404
    (get_object_or_404), not a silent success or redirect."""
    # Use a pk that is very unlikely to exist
    r = system_admin_client.post("/accounts/review/999999/approve/", {"effective_role": "viewer"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 5. Cross-user protection: profile view only shows the request user's data
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_profile_displays_own_data_not_other_users(officer_client, officer):
    """The profile page must display the authenticated user's own data,
    not any other user's. Since the view uses request.user (not a URL
    parameter), there is no way to view another user's profile.

    We verify this by checking that the officer's own full_name appears
    and a different user's full_name does NOT appear.
    """
    other = User.objects.create(
        username="phase_c_other_officer",
        full_name="Other Unique Name",
        role="extension_officer",
        approval_status="approved",
        is_active=True,
    )
    r = officer_client.get("/accounts/profile/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The officer's own full_name must appear
    assert officer.full_name in html, (
        f"Profile page must show the authenticated user's full_name ({officer.full_name})"
    )
    # The other user's full_name must NOT appear
    assert other.full_name not in html, (
        f"Profile page must NOT show another user's full_name ({other.full_name})"
    )
