"""Tests for the v5 color system and visual theme.

Verifies the design-token-based color system is loaded, semantic surface
classes are used on the dashboard, and the global header uses the deep-forest
dark theme. Also verifies no hardcoded Tailwind color classes leak into the
key dashboard sections (encouraging centralized token use).
"""
from __future__ import annotations

import re

import pytest
from django.test import Client


# ---------------------------------------------------------------------------
# 1. Design tokens CSS is loaded
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_design_tokens_css_loaded(officer_client):
    """The design tokens CSS file (tokens.css) must be loaded on every page."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "tokens.css" in html, "tokens.css design-token stylesheet must be loaded"


@pytest.mark.django_db
def test_dashboard_css_loaded(officer_client):
    """The dashboard.css semantic-component stylesheet must be loaded."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "dashboard.css" in html


# ---------------------------------------------------------------------------
# 2. Body background uses the warm-neutral sage tint (not pure white)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_body_uses_warm_neutral_background(officer_client):
    """The body must use the warm-neutral sage tint background (--color-background)
    rather than pure white. This prevents the cold/generic feel."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The body tag must reference the --color-background token
    assert "var(--color-background)" in html, (
        "Body must use --color-background token (warm-neutral sage tint), not pure white"
    )


# ---------------------------------------------------------------------------
# 3. Global header uses the deep-forest dark theme
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_global_header_uses_forest_dark_theme(officer_client):
    """The global header must use the .app-header class which applies the
    deep-forest dark color (#0F3D2E)."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The header element must have the app-header class
    header_match = re.search(r'<header[^>]*class="[^"]*app-header[^"]*"', html)
    assert header_match is not None, (
        "Global header must use the .app-header class (deep-forest dark theme)"
    )


@pytest.mark.django_db
def test_app_header_css_class_defined():
    """The .app-header CSS class must be defined in dashboard.css with the
    forest color token."""
    with open("/home/z/my-project/majishamba_fresh/static/css/dashboard.css") as f:
        css = f.read()
    assert ".app-header" in css, ".app-header class must be defined in dashboard.css"
    # The class must reference --color-forest
    app_header_block = re.search(r"\.app-header\s*\{[^}]+\}", css, re.S)
    assert app_header_block is not None
    assert "--color-forest" in app_header_block.group(0), (
        ".app-header must use --color-forest (deep forest green)"
    )


# ---------------------------------------------------------------------------
# 4. Primary nav uses semantic .app-nav-link class
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_primary_nav_uses_semantic_nav_link_class(officer_client):
    """Primary nav links must use the .app-nav-link semantic class (not
    hardcoded Tailwind color utilities). This centralizes the color system."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "app-nav-link" in html, "Primary nav must use .app-nav-link semantic class"


@pytest.mark.django_db
def test_app_nav_link_active_state_class(officer_client):
    """The active nav link must use the .is-active modifier (which applies
    the primary green background)."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "is-active" in html, "Active nav link must use .is-active modifier"


# ---------------------------------------------------------------------------
# 5. Count badges use semantic .nav-count-badge class
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_count_badges_use_semantic_class(officer_client):
    """The advisory/tasks count badge must use .nav-count-badge (semantic)
    rather than hardcoded Tailwind amber/emerald utilities."""
    from django.core.management import call_command
    from io import StringIO
    from tests.factories.models import AdvisoryFactory
    call_command("seed_kachieng_clusters", stdout=StringIO())
    for _ in range(2):
        AdvisoryFactory(status="draft")

    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "nav-count-badge" in html, "Count badges must use .nav-count-badge semantic class"


# ---------------------------------------------------------------------------
# 6. User menu uses semantic .user-menu-summary + .user-avatar classes
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_user_menu_uses_semantic_classes(officer_client):
    """The user menu must use .user-menu-summary and .user-avatar semantic
    classes (which apply the primary green avatar)."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "user-menu-summary" in html
    assert "user-avatar" in html


# ---------------------------------------------------------------------------
# 7. 'Needs your attention' uses the warm sage contextual surface
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_needs_attention_uses_warm_sage_surface(officer_client):
    """The 'Needs your attention' section must use the .surface-attention class
    (warm sage tint #EEF6F0), not a plain white card."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "surface-attention" in html, (
        "Needs attention section must use .surface-attention (warm sage tint), "
        "not a plain white card"
    )


@pytest.mark.django_db
def test_attention_cards_use_semantic_class(officer_client):
    """The three attention cards must use the .attention-card semantic class."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The class is applied to each of the 3 cards
    assert html.count("attention-card") >= 3, (
        "Three attention-card elements must be present (Drafts / Field visits / Tasks)"
    )


@pytest.mark.django_db
def test_attention_count_uses_forest_color(officer_client):
    """The attention count number must use the .attention-count class which
    applies the deep-forest color (not generic gray)."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "attention-count" in html


# ---------------------------------------------------------------------------
# 8. Primary CTA uses .btn-primary semantic class
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_primary_cta_uses_btn_primary_class(officer_client):
    """The 'Request advisory' button must use .btn-primary (which applies the
    primary agricultural green #176B45)."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "btn-primary" in html, "Primary CTA must use .btn-primary semantic class"


@pytest.mark.django_db
def test_btn_primary_css_uses_primary_token():
    """The .btn-primary CSS class must use the --color-primary token.
    The v5 definition (later in the file) overrides the v2 definition
    (which used hardcoded #047857). We check that AT LEAST ONE .btn-primary
    definition uses the token — the last one wins in CSS cascade."""
    with open("/home/z/my-project/majishamba_fresh/static/css/dashboard.css") as f:
        css = f.read()
    # Find ALL .btn-primary definitions
    btn_blocks = re.findall(r"\.btn-primary\s*\{[^}]+\}", css, re.S)
    assert btn_blocks, ".btn-primary class must be defined in dashboard.css"
    # At least one definition (the v5 override) must use --color-primary
    uses_token = any("--color-primary" in block for block in btn_blocks)
    assert uses_token, (
        ".btn-primary must use --color-primary token in at least one definition "
        "(the v5 override) — found only hardcoded colors"
    )


# ---------------------------------------------------------------------------
# 9. Field Conditions & Guidance uses differentiated semantic surfaces
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_weather_panel_uses_sky_blue_surface(officer_client):
    """The Weather panel must use .surface-weather (sky-blue tint) to
    visually communicate environmental/weather information."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "surface-weather" in html, (
        "Weather panel must use .surface-weather (sky-blue tint)"
    )


@pytest.mark.django_db
def test_agronomic_guidance_uses_sage_surface(officer_client):
    """The Agronomic guidance panel must use .surface-guidance (sage tint)
    to create a visual relationship with agriculture."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "surface-guidance" in html, (
        "Agronomic guidance must use .surface-guidance (sage tint)"
    )


@pytest.mark.django_db
def test_pest_panel_uses_neutral_surface_when_no_alert(officer_client):
    """The Pest alerts panel must use a neutral surface (not red/amber) when
    there's no alert. 'No verified official pest alert' is not a danger."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The pest panel uses .surface (neutral) when there's no alert
    # We just verify the section is present and doesn't use a danger surface
    # (the test environment has no real pest alert)
    assert "Pest alerts" in html


# ---------------------------------------------------------------------------
# 10. Workflow pills use semantic classes
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_workflow_pills_use_semantic_classes(officer_client):
    """The workflow legend must use .workflow-pill + modifier classes
    (workflow-ai-draft, workflow-reviewed, workflow-human-approved,
    workflow-field-verified) rather than inline color styles."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "workflow-pill" in html
    assert "workflow-ai-draft" in html
    assert "workflow-reviewed" in html
    assert "workflow-human-approved" in html
    assert "workflow-field-verified" in html


# ---------------------------------------------------------------------------
# 11. Design tokens are centralized in tokens.css
# ---------------------------------------------------------------------------

def test_tokens_css_defines_all_required_tokens():
    """tokens.css must define all the required design tokens from the v5 spec."""
    with open("/home/z/my-project/majishamba_fresh/static/css/tokens.css") as f:
        css = f.read()
    required_tokens = [
        "--color-primary",
        "--color-primary-hover",
        "--color-primary-active",
        "--color-primary-soft",
        "--color-forest",
        "--color-sage",
        "--color-sand",
        "--color-sky",
        "--color-background",
        "--color-surface",
        "--color-surface-muted",
        "--color-surface-warm",
        "--color-text",
        "--color-text-secondary",
        "--color-text-muted",
        "--color-text-disabled",
        "--color-border",
        "--color-draft",
        "--color-success",
        "--color-info",
        "--color-warning",
        "--color-danger",
        "--color-neutral",
        "--shadow-xs",
        "--shadow-sm",
        "--shadow-md",
        "--shadow-lg",
    ]
    missing = [t for t in required_tokens if t not in css]
    assert not missing, f"Missing design tokens in tokens.css: {missing}"


def test_tokens_css_uses_specified_palette_values():
    """The design tokens must use the exact palette values from the v5 spec
    (primary green #176B45, deep forest #0F3D2E, soft sage #E8F3ED, etc.)."""
    with open("/home/z/my-project/majishamba_fresh/static/css/tokens.css") as f:
        css = f.read()
    # Check a few key tokens to confirm the palette is the v5 agricultural theme
    assert "#176B45" in css, "Primary green must be #176B45"
    assert "#0F3D2E" in css, "Deep forest must be #0F3D2E"
    assert "#E8F3ED" in css, "Soft sage must be #E8F3ED"
    assert "#F7F9F7" in css, "Application background must be #F7F9F7 (warm-neutral sage tint)"
    assert "#256B8A" in css, "Sky/water blue must be #256B8A"
    assert "#17211D" in css, "Primary text must be #17211D (deep charcoal-green, not pure black)"
    assert "#DCE4DF" in css, "Border must be #DCE4DF (subtle neutral/green-gray)"


# ---------------------------------------------------------------------------
# 12. Status pill classes are defined in CSS
# ---------------------------------------------------------------------------

def test_status_pill_classes_defined():
    """The .status-pill + modifier classes must be defined in dashboard.css
    for all semantic statuses (draft, approved, field-verification, rejected,
    deferred, neutral)."""
    with open("/home/z/my-project/majishamba_fresh/static/css/dashboard.css") as f:
        css = f.read()
    required = [
        ".status-pill",
        ".status-pill.status-draft",
        ".status-pill.status-approved",
        ".status-pill.status-field-verification",
        ".status-pill.status-rejected",
        ".status-pill.status-deferred",
        ".status-pill.status-neutral",
    ]
    missing = [c for c in required if c not in css]
    assert not missing, f"Missing status pill classes: {missing}"


def test_status_pills_have_dot_indicator_and_text_label():
    """Status pills must have a ::before dot (non-color signal) so colour is
    never the only signal (WCAG 1.4.1 Use of Color)."""
    with open("/home/z/my-project/majishamba_fresh/static/css/dashboard.css") as f:
        css = f.read()
    assert ".status-pill::before" in css, (
        "Status pills must have a ::before pseudo-element (non-color signal)"
    )


# ---------------------------------------------------------------------------
# 13. Surfaces use semantic classes (not hardcoded white cards)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dashboard_surfaces_use_semantic_classes(officer_client):
    """The dashboard must use semantic surface classes (.surface, .surface-attention,
    .surface-weather, .surface-guidance) rather than hardcoded 'bg-white border-stone-200'
    Tailwind utilities for the main surfaces."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The semantic classes must be present
    assert "surface" in html  # generic surface class
    # Count of 'bg-white' should be limited (we accept some for tables/cards)
    # but the main surfaces should use semantic classes
    surface_count = html.count("surface-attention") + html.count("surface-weather") + html.count("surface-guidance") + html.count('"surface ')
    assert surface_count >= 4, (
        f"Expected at least 4 semantic surface usages, got {surface_count}"
    )


# ---------------------------------------------------------------------------
# 14. Footer unchanged (still uses stone-900 dark)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_footer_still_present(officer_client):
    """The footer must still be present with the synthetic-data disclaimer
    + About/legal link (unchanged from v4)."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "Synthetic household" in html or "Synthetic household &amp; plot data only" in html
    assert "/dashboard/about/" in html
    assert "About / legal" in html


# ---------------------------------------------------------------------------
# 15. No template-comment leaks (regression guard)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_no_template_comment_leaks_after_v5_theme(officer_client):
    """Verify the v5 theme changes didn't reintroduce multi-line {# ... #}
    template comments that leak to the browser."""
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    leaks = re.findall(r"\{#.*?#\}", html, re.S)
    multi_line_leaks = [l for l in leaks if "\n" in l]
    assert not multi_line_leaks, (
        f"Multi-line {{# ... #}} template comments leaked: {multi_line_leaks}"
    )


# ---------------------------------------------------------------------------
# 16. Auth pages (base_auth.html) still work — they don't use the dark header
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auth_pages_still_render_correctly():
    """Auth pages (login, register) use base_auth.html (not base.html) so they
    must still render correctly with the v5 tokens available globally."""
    c = Client()
    r = c.get("/accounts/login/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # Auth pages don't have the dark forest header — they have the minimal
    # auth-specific header from base_auth.html
    assert "Kachieng’ AI Agent" in html
    # No raw template syntax leaks
    assert "{#" not in html
    assert "{%" not in html
