"""Tests for production readiness: officer creation, health endpoint, empty states."""
from __future__ import annotations

import pytest
from django.core.management import call_command
from io import StringIO
from django.test import Client


@pytest.mark.django_db
def test_create_officer_command():
    """The create_officer command creates an account with unusable password."""
    call_command("create_officer",
                 username="jdoe",
                 full_name="John Doe",
                 role="extension_officer",
                 stdout=StringIO())
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = User.objects.get(username="jdoe")
    assert u.role == "extension_officer"
    assert u.full_name == "John Doe"
    assert u.sub_county == "Nyatike"
    assert u.ward == "Kachieng"
    assert u.is_staff is True
    # Password should be unusable until set via changepassword
    assert not u.has_usable_password()
    # Login should fail
    c = Client()
    r = c.post("/accounts/login/", {"username": "jdoe", "password": "anything"})
    assert r.status_code == 200  # login failed, re-rendered form


@pytest.mark.django_db
def test_create_officer_duplicate_rejected():
    """Creating a duplicate username raises an error."""
    call_command("create_officer",
                 username="jdoe", full_name="John Doe", role="extension_officer",
                 stdout=StringIO())
    with pytest.raises(Exception):
        call_command("create_officer",
                     username="jdoe", full_name="Another", role="supervisor",
                     stdout=StringIO())


@pytest.mark.django_db
def test_health_endpoint():
    """The health endpoint returns JSON with database and provider status."""
    c = Client()
    r = c.get("/health/health/")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "degraded")
    assert "database" in data
    assert "llm_provider" in data
    assert "version" in data


@pytest.mark.django_db
def test_production_mode_hides_demo_cards():
    """When DEMO_MODE=False, the login page does NOT show demo account cards."""
    from django.conf import settings
    settings.MAJISHAMBA["DEMO_MODE"] = False
    settings.DEBUG = True
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "Choose a demo account" not in html
    assert "Synthetic demo account" not in html


@pytest.mark.django_db
def test_deploy_script_does_not_load_fixtures():
    """The production deploy script does NOT load demo fixtures."""
    with open("scripts/deploy_production.sh", "r") as f:
        content = f.read()
    assert "loaddata" not in content, "Deploy script loads fixtures — should NOT in production!"
    assert "load_demo_data" not in content, "Deploy script creates demo users — should NOT in production!"
    assert "create_officer" in content, "Deploy script should mention create_officer for real account setup"


@pytest.mark.django_db
def test_secrets_absent_from_health():
    """The health endpoint does not expose API keys or secrets."""
    c = Client()
    r = c.get("/health/health/")
    html = r.content.decode("utf-8")
    assert "sk-or-v1" not in html
    assert "SECRET" not in html.upper() or "SECRET_KEY" not in html
    assert "PASSWORD" not in html.upper()
