"""Tests for the minimal public auth header on login/register/registration_pending pages.

These tests verify the requirements of the public-auth-header redesign:

  * Minimal header — only logo + Sign in / Create account links.
  * No application-section nav (Dashboard, Map, Advisories, Tasks, Audit, Data).
  * No geographic subtitle.
  * Logo links to /accounts/login/, NOT to /dashboard/.
  * Skip link to main content present and target exists.
  * Service description line present below header.
  * Primary action is emphasized per page:
      - login page  → "Sign in" emphasized
      - register    → "Create account" emphasized
  * Responsive (sm:flex-row) header classes present.
  * Accessible focus state classes present.
  * No demo or synthetic references anywhere on auth pages.
"""
from __future__ import annotations

import pytest
from django.test import Client


# ---------------------------------------------------------------------------
# Minimal-header presence
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_page_has_minimal_public_header():
    """Login page header contains only the logo + Sign in / Create account — no app nav."""
    c = Client()
    r = c.get("/accounts/login/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")

    # Required header elements
    assert "Kachieng’ AI Agent" in html, "Logo / brand text missing"
    assert 'href="/accounts/login/"' in html, "Sign in link missing"
    assert 'href="/accounts/register/"' in html, "Create account link missing"

    # App-section nav links MUST NOT appear in the header
    # (note: these strings can legitimately appear in app navbar of authenticated
    #  pages — but never on the auth pages, which use base_auth.html)
    assert "Dashboard" not in html, "App nav link 'Dashboard' leaked onto login page"
    assert "Advisories" not in html, "App nav link 'Advisories' leaked onto login page"
    assert "Tasks" not in html, "App nav link 'Tasks' leaked onto login page"
    assert "Audit" not in html, "App nav link 'Audit' leaked onto login page"
    assert ">Map<" not in html, "App nav link 'Map' leaked onto login page"
    assert ">Data<" not in html, "App nav link 'Data' leaked onto login page"


@pytest.mark.django_db
def test_register_page_has_minimal_public_header():
    """Register page header contains only the logo + Sign in / Create account — no app nav."""
    c = Client()
    r = c.get("/accounts/register/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")

    assert "Kachieng’ AI Agent" in html
    assert 'href="/accounts/login/"' in html
    assert 'href="/accounts/register/"' in html

    assert "Dashboard" not in html
    assert "Advisories" not in html
    assert "Tasks" not in html
    assert "Audit" not in html


@pytest.mark.django_db
def test_registration_pending_page_has_minimal_public_header():
    """registration_pending page header contains only logo + Sign in / Create account."""
    c = Client()
    r = c.get("/accounts/registration/pending/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")

    assert "Kachieng’ AI Agent" in html
    assert 'href="/accounts/login/"' in html
    assert 'href="/accounts/register/"' in html

    assert "Dashboard" not in html
    assert "Advisories" not in html


# ---------------------------------------------------------------------------
# No geographic subtitle on auth pages
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_no_geographic_subtitle_on_auth_pages():
    """The geographic subtitle line must not appear on any auth page."""
    c = Client()
    geo_phrase = "Kachieng Ward · Nyatike Sub-County · Migori County, Kenya"
    for url in ["/accounts/login/", "/accounts/register/", "/accounts/registration/pending/"]:
        r = c.get(url)
        assert r.status_code == 200, f"{url} returned {r.status_code}"
        assert geo_phrase not in r.content.decode("utf-8"), f"Geographic subtitle still present on {url}"


# ---------------------------------------------------------------------------
# Logo links to /accounts/login/, NOT /dashboard/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_logo_links_to_login_not_dashboard():
    """The header logo on auth pages must link to /accounts/login/ (public landing), not /dashboard/."""
    c = Client()
    for url in ["/accounts/login/", "/accounts/register/", "/accounts/registration/pending/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        # The logo <a> tag must point at /accounts/login/.
        # We accept any <a ... href="/accounts/login/" ...> that contains "Kachieng’ AI Agent".
        # The simplest robust assertion: at least one occurrence of the brand-text inside
        # an anchor pointing at /accounts/login/.
        assert 'href="/accounts/login/"' in html, f"Logo missing /accounts/login/ link on {url}"
        # And the dashboard link must NOT be the logo target on auth pages.
        # The base_auth.html template has no link to /dashboard/ at all.
        # If a link to /dashboard/ exists, it's a regression.
        # (defensive: the only allowed occurrence of "dashboard" in href form is none at all)
        assert 'href="/dashboard/"' not in html, f"Dashboard link leaked onto auth page {url}"


# ---------------------------------------------------------------------------
# Skip link + main content target
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_skip_link_present_on_auth_pages():
    """Each auth page must have a skip link pointing to #main-content."""
    c = Client()
    for url in ["/accounts/login/", "/accounts/register/", "/accounts/registration/pending/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        assert 'class="skip-link"' in html, f"Skip link missing on {url}"
        assert 'href="#main-content"' in html, f"Skip link target missing on {url}"
        assert 'id="main-content"' in html, f"main-content id missing on {url}"


@pytest.mark.django_db
def test_main_content_is_focusable_for_skip_link():
    """The main element on auth pages must be focusable so the skip link lands properly."""
    c = Client()
    for url in ["/accounts/login/", "/accounts/register/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        # The <main> element must carry tabindex="-1" so it can receive focus.
        assert 'tabindex="-1"' in html, f"main element not focusable on {url}"


# ---------------------------------------------------------------------------
# Service description line below header
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_service_description_line_present():
    """The service description / brand subtitle must appear somewhere on the page
    (either in the header or in the brand panel). The v7 auth theme removed the
    redundant standalone service-description line (it duplicated the header
    subtitle) and instead shows it in the brand panel on desktop + the header
    brand subtitle on all screens."""
    c = Client()
    for url in ["/accounts/login/", "/accounts/register/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        # The brand subtitle 'Climate-smart agricultural advisories' must appear
        # (it's in the header brand area + the brand panel on desktop)
        assert "Climate-smart agricultural advisories" in html, (
            f"Brand subtitle missing on {url}"
        )


# ---------------------------------------------------------------------------
# Primary action emphasis per page
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_page_emphasizes_sign_in():
    """On the login page, the 'Sign in' link in the header must be marked active (aria-current=page)."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    # The Sign in link must carry aria-current="page"
    assert 'aria-current="page"' in html, "No active-page marker on login header"
    # Both Sign in and Create account links must be present in the header nav.
    assert "Sign in" in html
    assert "Create account" in html


@pytest.mark.django_db
def test_register_page_emphasizes_create_account():
    """On the register page, the 'Create account' link must be marked active (aria-current=page)."""
    c = Client()
    r = c.get("/accounts/register/")
    html = r.content.decode("utf-8")
    assert 'aria-current="page"' in html, "No active-page marker on register header"
    assert "Sign in" in html
    assert "Create account" in html


@pytest.mark.django_db
def test_registration_pending_does_not_emphasize_either():
    """registration_pending is a status page — neither Sign in nor Create account is the 'current' page."""
    c = Client()
    r = c.get("/accounts/registration/pending/")
    html = r.content.decode("utf-8")
    assert 'aria-current="page"' not in html, "Unexpected active-page marker on registration_pending"


# ---------------------------------------------------------------------------
# Responsive header (sm:flex-row)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auth_header_responsive_classes_present():
    """The header must include responsive flex-row classes so it stacks on narrow screens."""
    c = Client()
    for url in ["/accounts/login/", "/accounts/register/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        # sm:flex-row ensures horizontal layout on small+ screens; on phones it stacks.
        assert "sm:flex-row" in html, f"Responsive flex-row class missing on {url}"
        assert "sm:justify-between" in html or "justify-between" in html, f"Header justify-between missing on {url}"


# ---------------------------------------------------------------------------
# Focus-visible outlines on auth pages
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auth_pages_have_focus_visible_styles():
    """All interactive elements on auth pages must have focus-visible outlines.
    The v5 theme uses CSS classes (.auth-nav-link:focus-visible, .auth-input:focus,
    .btn-primary:focus-visible) which define the outline in dashboard.css — so
    we check that the CSS file is loaded (which provides the focus styles) AND
    that the semantic classes that carry those focus styles are present."""
    c = Client()
    for url in ["/accounts/login/", "/accounts/register/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        # The dashboard.css (which defines the focus styles) must be loaded
        assert "dashboard.css" in html, f"dashboard.css missing on {url} (provides focus styles)"
        # The semantic classes that carry focus-visible styles must be present
        # (auth-nav-link, auth-input, btn-primary, auth-brand all have :focus-visible)
        has_focus_class = (
            "auth-nav-link" in html or
            "auth-input" in html or
            "btn-primary" in html or
            "auth-brand" in html or
            "focus-visible:outline" in html  # backward-compat with old template
        )
        assert has_focus_class, f"focus-visible semantic classes missing on {url}"


# ---------------------------------------------------------------------------
# No demo / synthetic references on auth pages
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_no_demo_or_synthetic_references_on_auth_pages():
    """No 'demo', 'synthetic', 'DEMO_MODE' or 'nyatike_officer' strings may appear on auth pages."""
    c = Client()
    banned_substrings = [
        "nyatike_officer",
        "nyatike_supervisor",
        "nyatike_viewer",
        "majishamba-demo",
        "Choose a demo account",
        "Synthetic demo account",
        "Demo mode is ON",
        "DEMO_MODE",
        "demo account selector",
    ]
    for url in ["/accounts/login/", "/accounts/register/", "/accounts/registration/pending/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        for needle in banned_substrings:
            assert needle not in html, f"Banned reference {needle!r} found on {url}"


# ---------------------------------------------------------------------------
# Authenticated users still see the full app navbar (regression guard)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_authenticated_users_still_see_app_navbar(officer_client):
    """Authenticated users on operational pages must still see the full application navbar
    with role-aware items (Dashboard, Advisories, Tasks, Audit, etc.)."""
    r = officer_client.get("/dashboard/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Dashboard" in html, "App navbar missing Dashboard link for authenticated officer"
    assert "Advisories" in html, "App navbar missing Advisories link for authenticated officer"
    assert "Tasks" in html, "App navbar missing Tasks link for authenticated officer"
    assert "Audit" in html, "App navbar missing Audit link for authenticated officer"
    # Logo on app pages should link to dashboard (current behavior).
    assert 'href="/dashboard/"' in html, "App page logo should link to /dashboard/"


# ---------------------------------------------------------------------------
# Auth pages use base_auth.html, not base.html (structural assertion)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auth_pages_extend_base_auth_not_base():
    """Auth pages must NOT include operational-page-only assets like htmx or maplibre-gl,
    which are only loaded by base.html. Their presence indicates the wrong base template."""
    c = Client()
    for url in ["/accounts/login/", "/accounts/register/", "/accounts/registration/pending/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        # htmx and maplibre-gl are only used by the operational app — not on auth pages.
        assert "htmx.org" not in html, f"htmx loaded on auth page {url} — wrong base template"
        assert "maplibre-gl" not in html, f"maplibre-gl loaded on auth page {url} — wrong base template"
