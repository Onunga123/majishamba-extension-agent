"""Branding tests — verify Kachieng AI Agent name is used everywhere user-facing."""
from __future__ import annotations

import pytest
from django.test import Client


@pytest.mark.django_db
def test_login_page_shows_kachieng_ai_agent():
    """The login page must show 'Kachieng AI Agent' as the product name."""
    c = Client()
    r = c.get("/accounts/login/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Kachieng AI Agent" in html, "Login page must show 'Kachieng AI Agent'"
    # Old name must NOT appear in user-facing text
    assert "MajiShamba" not in html, "Login page must not show old 'MajiShamba' name"


@pytest.mark.django_db
def test_login_page_shows_service_description():
    """The login page must show the minimal service description line below the header.
    (The old taglines 'Climate-smart advisories. Extension officers decide.' and
    'Access agricultural advisories, field tasks and evidence review.' have been
    removed from the login card as part of the minimal-auth redesign.)"""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    # The new base_auth.html includes a single short description line below the header.
    assert "Climate-smart agricultural advisories for extension officers in Kachieng Ward." in html, (
        "Login page must show the short service description line below the header"
    )
    # The old card-level taglines must NOT appear
    assert "Climate-smart advisories. Extension officers decide." not in html, (
        "Old tagline should have been removed from the login card"
    )
    assert "Access agricultural advisories, field tasks and evidence review" not in html, (
        "Old second tagline should have been removed from the login card"
    )


@pytest.mark.django_db
def test_dashboard_shows_kachieng_ai_agent(officer_client):
    r = officer_client.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Kachieng AI Agent" in html
    assert "MajiShamba" not in html


@pytest.mark.django_db
def test_advisories_list_shows_kachieng_ai_agent(officer_client):
    r = officer_client.get("/advisories/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Kachieng AI Agent" in html
    assert "MajiShamba" not in html


@pytest.mark.django_db
def test_tasks_list_shows_kachieng_ai_agent(officer_client):
    r = officer_client.get("/tasks/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "MajiShamba" not in html  # tasks list page should not have old branding


@pytest.mark.django_db
def test_audit_list_shows_kachieng_ai_agent(officer_client):
    r = officer_client.get("/audit/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "MajiShamba" not in html


@pytest.mark.django_db
def test_map_page_shows_kachieng_ai_agent(officer_client):
    r = officer_client.get("/dashboard/map/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Kachieng AI Agent" in html
    assert "MajiShamba" not in html
