"""Tests for System Administrator account provisioning."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client


User = get_user_model()


def account_payload(username: str, role: str = "viewer") -> dict[str, str]:
    return {
        "full_name": f"Created {role}",
        "username": username,
        "email": f"{username}@example.com",
        "role": role,
        "organization": "Nyatike Office",
        "sub_county": "Nyatike",
        "ward": "Kachieng",
        "password1": "secure-admin-created-password",
        "password2": "secure-admin-created-password",
    }


@pytest.mark.django_db
def test_system_admin_can_open_user_management(system_admin):
    client = Client()
    client.force_login(system_admin)

    response = client.get("/accounts/users/")

    assert response.status_code == 200
    assert "Create user account" in response.content.decode("utf-8")


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["system_admin", "extension_officer", "supervisor", "viewer"])
def test_system_admin_can_create_each_role(system_admin, role):
    client = Client()
    client.force_login(system_admin)

    response = client.post("/accounts/users/", account_payload(f"created_{role}", role))

    assert response.status_code == 302
    user = User.objects.get(username=f"created_{role}")
    assert user.role == role
    assert user.requested_role == role
    assert user.approval_status == User.ApprovalStatus.APPROVED
    assert user.approved_by == system_admin
    assert user.approved_at is not None
    assert user.is_active is True
    assert user.check_password("secure-admin-created-password")
    assert user.password != "secure-admin-created-password"


@pytest.mark.django_db
def test_non_administrator_cannot_open_or_submit_user_management(viewer):
    client = Client()
    client.force_login(viewer)

    assert client.get("/accounts/users/").status_code == 403
    response = client.post("/accounts/users/", account_payload("forbidden_user", "system_admin"))

    assert response.status_code == 403
    assert not User.objects.filter(username="forbidden_user").exists()


@pytest.mark.django_db
def test_invalid_admin_account_input_does_not_create_user(system_admin):
    client = Client()
    client.force_login(system_admin)
    payload = account_payload("invalid_admin_input")
    payload["password2"] = "different-password"

    response = client.post("/accounts/users/", payload)

    assert response.status_code == 200
    assert not User.objects.filter(username="invalid_admin_input").exists()
    assert "Passwords do not match" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_admin_cannot_forge_staff_superuser_or_pending_fields(system_admin):
    client = Client()
    client.force_login(system_admin)
    payload = account_payload("forged_admin_fields", "viewer")
    payload.update({
        "is_staff": "true",
        "is_superuser": "true",
        "approval_status": User.ApprovalStatus.PENDING,
        "approved_by": str(system_admin.pk),
    })

    response = client.post("/accounts/users/", payload)

    assert response.status_code == 302
    user = User.objects.get(username="forged_admin_fields")
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.approval_status == User.ApprovalStatus.APPROVED
    assert user.approved_by == system_admin
