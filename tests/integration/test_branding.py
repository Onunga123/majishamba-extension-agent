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
def test_login_page_shows_tagline():
    """The login page must show the tagline."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "Climate-smart advisories" in html, "Login page must show the tagline"
    assert "Extension officers decide" in html


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
