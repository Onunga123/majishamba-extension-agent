"""Focused test: GET /accounts/login/ and assert the response does NOT contain
the old header subtitle / taglines / demo content.

This test exists because the user reported the old content was still
visible on the login page. The test is intentionally simple and isolated
so it can be run as a one-shot verification:

    .venv/bin/python -m pytest tests/integration/test_login_page_clean.py -v

If this test PASSES, the rendered HTML does not contain any of the
unwanted strings. If you still see them in your browser, the cause is
NOT the template — it's one of:

    1. The dev server is running an old checkout. Pull latest, restart.
    2. The browser is showing a cached page. Hard-refresh (Ctrl+Shift+R).
    3. You're looking at a screenshot from before the changes, not a
       live page.

The test queries Django directly (no browser, no cache), so it is the
authoritative answer.
"""
from __future__ import annotations

import pytest
from django.test import Client


@pytest.mark.django_db
def test_login_page_does_not_contain_old_header_subtitle_or_demo_content():
    """GET /accounts/login/ and assert the response does NOT contain the old
    header subtitle, the old taglines, or any demo-account section.

    Asserts absence of:
        - 'Kachieng Ward · Nyatike Sub-County'   (old geographic subtitle)
        - 'Climate-smart advisories. Extension officers decide.'  (old tagline)
        - 'Access agricultural advisories, field tasks'  (old second tagline)
        - 'Synthetic demo account'  (demo-account section)
    Also asserts presence of the new minimal header so the test isn't
    vacuously passing because the page 500'd.
    """
    c = Client()
    r = c.get("/accounts/login/")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    html = r.content.decode("utf-8")

    # --- Assertions: unwanted strings MUST be absent ---
    unwanted = [
        "Kachieng Ward · Nyatike Sub-County",
        "Climate-smart advisories. Extension officers decide.",
        "Access agricultural advisories, field tasks",
        "Synthetic demo account",
    ]
    for needle in unwanted:
        assert needle not in html, (
            f"UNWANTED STRING STILL PRESENT on /accounts/login/: {needle!r}. "
            f"The template in use is not the cleaned one. "
            f"Run 'git pull && uv run python manage.py runserver' to pick up the new template."
        )

    # --- Assertions: new minimal header MUST be present ---
    # (otherwise the test would pass even if the page 500'd or rendered empty)
    assert "Kachieng AI Agent" in html, "Brand text missing — page may have failed to render"
    assert "Sign in" in html, "Sign in text missing"
    assert 'href="/accounts/login/"' in html, "Sign in link missing"
    assert 'href="/accounts/register/"' in html, "Create account link missing"


@pytest.mark.django_db
def test_register_page_does_not_contain_old_header_subtitle_or_demo_content():
    """Same assertions for /accounts/register/."""
    c = Client()
    r = c.get("/accounts/register/")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    html = r.content.decode("utf-8")

    unwanted = [
        "Kachieng Ward · Nyatike Sub-County",
        "Climate-smart advisories. Extension officers decide.",
        "Access agricultural advisories, field tasks",
        "Synthetic demo account",
    ]
    for needle in unwanted:
        assert needle not in html, (
            f"UNWANTED STRING STILL PRESENT on /accounts/register/: {needle!r}."
        )

    # New minimal header must be present
    assert "Kachieng AI Agent" in html
    assert "Create account" in html or "Request access" in html


@pytest.mark.django_db
def test_login_page_does_not_extend_base_html_operational_footer():
    """The login page must NOT show the operational footer from base.html
    (the 'Kachieng AI Agent — MIT licence · …' line and the 'Synthetic
    household & plot data only' line)."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "Kachieng AI Agent — MIT licence" not in html, (
        "Operational footer from base.html is leaking onto the login page — "
        "the login template is extending the wrong base template."
    )
    assert "Synthetic household & plot data only" not in html
    assert "Synthetic household &amp; plot data only" not in html  # HTML-escaped form


@pytest.mark.django_db
def test_login_template_origin_is_base_auth_html():
    """Definitive proof: the file Django loads for 'accounts/login.html'
    must live at templates/accounts/login.html and must extend base_auth.html."""
    import os
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    django.setup()
    from django.template.loader import get_template

    login_tmpl = get_template("accounts/login.html")
    login_path = login_tmpl.origin.name
    assert login_path.endswith("templates/accounts/login.html"), (
        f"Login template resolved to unexpected path: {login_path}"
    )

    with open(login_path, "r") as f:
        first_line = f.readline().rstrip()
    assert first_line == '{% extends "base_auth.html" %}', (
        f"Login template does not extend base_auth.html — first line: {first_line!r}"
    )

    # And base_auth.html must exist at templates/base_auth.html
    base_tmpl = get_template("base_auth.html")
    base_path = base_tmpl.origin.name
    assert base_path.endswith("templates/base_auth.html"), (
        f"base_auth.html resolved to unexpected path: {base_path}"
    )
