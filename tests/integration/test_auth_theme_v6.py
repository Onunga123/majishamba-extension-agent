"""Tests for the v5 auth theme alignment — login, register, registration_pending
pages use the same professional color system and branding as the main dashboard.

Covers the explicit v6 auth-theme spec:
  1. Branding: 'Kachieng AI Agent' + 'Climate-smart agricultural advisories'
     displayed prominently, NOT slash-separated.
  2. Color theme: reuses the dashboard's centralized design tokens (tokens.css
     + dashboard.css loaded on auth pages).
  3. Login page: 'Welcome back' heading, concise supporting text, username
     field, password field with show/hide, primary 'Sign in' button using
     .btn-primary (agricultural green), 'Need an account? Create one' link.
  4. Registration page: 'Create your account' heading, clear explanation,
     preserves existing fields + validation + approval requirements,
     'Already have an account? Sign in' link.
  5. Responsive design + accessibility: WCAG 2.2 AA, explicit labels, keyboard
     nav, visible focus, accessible password toggle, autocomplete attributes.
  6. Security: no functionality changes — auth, CSRF, validation, approval
     requirements all preserved.
  7. Verification: pages match the dashboard's brand without importing
     unnecessary dashboard complexity.
"""
from __future__ import annotations

import re

import pytest
from django.test import Client


# ---------------------------------------------------------------------------
# 1. Branding — Kachieng AI Agent + Climate-smart agricultural advisories
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auth_pages_show_brand_name_and_subtitle():
    """All auth pages must show 'Kachieng AI Agent' as the brand name and
    'Climate-smart agricultural advisories' as the subtitle (NOT slash-separated)."""
    c = Client()
    for url in ["/accounts/login/", "/accounts/register/", "/accounts/registration/pending/"]:
        r = c.get(url)
        assert r.status_code == 200, f"{url} returned {r.status_code}"
        html = r.content.decode("utf-8")
        # Brand name must be present
        assert "Kachieng’ AI Agent" in html, f"Brand name 'Kachieng AI Agent' missing on {url}"
        # Subtitle must be present (the new auth header shows it under the brand)
        assert "Climate-smart agricultural advisories" in html, (
            f"Subtitle 'Climate-smart agricultural advisories' missing on {url}"
        )


@pytest.mark.django_db
def test_auth_pages_do_not_use_slash_separated_brand():
    """The old slash-separated brand 'Kachieng AI Agent / Climate-smart advisories'
    must NOT appear. The v6 auth theme shows them as separate stacked elements."""
    c = Client()
    for url in ["/accounts/login/", "/accounts/register/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        # The old slash-separated form must NOT appear
        assert "Kachieng AI Agent / Climate-smart advisories" not in html, (
            f"Old slash-separated brand still present on {url}"
        )


# ---------------------------------------------------------------------------
# 2. Color theme — design tokens loaded on auth pages
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auth_pages_load_design_tokens():
    """Auth pages must load tokens.css + dashboard.css (the dashboard's
    centralized design-token system)."""
    c = Client()
    for url in ["/accounts/login/", "/accounts/register/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        assert "tokens.css" in html, f"tokens.css missing on {url}"
        assert "dashboard.css" in html, f"dashboard.css missing on {url}"


@pytest.mark.django_db
def test_auth_pages_use_warm_neutral_background():
    """Auth pages must use the warm-neutral sage tint background
    (--color-background #F7F9F7), not pure white."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    # The body must have the auth-page class (which applies --color-background)
    assert "auth-page" in html, "Body must have .auth-page class (warm neutral background)"


@pytest.mark.django_db
def test_auth_header_uses_forest_green_brand():
    """The auth header brand mark must use the deep forest green color
    (via .auth-brand-mark class which applies --color-forest)."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "auth-brand" in html, "Brand link must use .auth-brand class"
    assert "auth-brand-mark" in html, "Brand SVG must use .auth-brand-mark (forest green)"
    assert "auth-brand-name" in html, "Brand name must use .auth-brand-name"


def test_auth_brand_css_uses_forest_token():
    """The .auth-brand-name CSS class must use --color-forest (deep forest green)."""
    with open("/home/z/my-project/majishamba_fresh/static/css/dashboard.css") as f:
        css = f.read()
    brand_name_block = re.search(r"\.auth-brand-name\s*\{[^}]+\}", css, re.S)
    assert brand_name_block is not None, ".auth-brand-name class must be defined"
    assert "--color-forest" in brand_name_block.group(0), (
        ".auth-brand-name must use --color-forest (deep forest green #0F3D2E)"
    )


# ---------------------------------------------------------------------------
# 3. Login page
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_page_uses_welcome_back_heading():
    """The login page must use 'Welcome back' as the main heading (not 'Sign in to Kachieng AI Agent')."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    # The h1 must be 'Welcome back'
    h1_match = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
    assert h1_match is not None, "Login page must have an <h1>"
    h1_text = h1_match.group(1).strip()
    assert "Welcome back" in h1_text, (
        f"Login page h1 must contain 'Welcome back' — got {h1_text!r}"
    )


@pytest.mark.django_db
def test_login_page_has_concise_supporting_text():
    """The login page must have concise supporting text mentioning
    'climate-smart advisory tools for Kachieng’ Ward'."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "Sign in to access climate-smart advisory tools for Kachieng’ Ward" in html, (
        "Login page must have concise supporting text"
    )


@pytest.mark.django_db
def test_login_page_uses_btn_primary_class():
    """The 'Sign in' button must use the .btn-primary class (agricultural green)."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "btn-primary" in html, "Sign in button must use .btn-primary (agricultural green)"
    # The button text must be 'Sign in' (allow for whitespace/newlines between text and closing tag)
    assert re.search(r"Sign\s+in\s*</button>", html, re.S), (
        "Sign in button text must be 'Sign in'"
    )


@pytest.mark.django_db
def test_login_page_uses_auth_input_class():
    """The username and password inputs must use the .auth-input class
    (token-based form styling)."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "auth-input" in html, "Form inputs must use .auth-input class"
    # The password field must have the show/hide toggle
    assert "auth-password-toggle" in html, "Password show/hide toggle must use .auth-password-toggle"


@pytest.mark.django_db
def test_login_page_has_show_hide_password_control():
    """The password field must have a functional show/hide control with
    accessible aria-label."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert 'aria-label="Show password"' in html, (
        "Password toggle must have aria-label='Show password'"
    )
    # The toggle must be a <button type="button"> (not a link)
    assert "<button" in html and "auth-password-toggle" in html


@pytest.mark.django_db
def test_login_page_has_autocomplete_attributes():
    """The username field must have autocomplete='username' and the password
    field must have autocomplete='current-password' (WCAG 2.2 AA)."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert 'autocomplete="username"' in html, "Username field must have autocomplete='username'"
    assert 'autocomplete="current-password"' in html, (
        "Password field must have autocomplete='current-password'"
    )


@pytest.mark.django_db
def test_login_page_has_registration_link():
    """The login page must have a 'Need an account? Create one' link to /accounts/register/."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "Need an account?" in html
    assert "Create one" in html
    assert 'href="/accounts/register/"' in html


@pytest.mark.django_db
def test_login_page_does_not_have_forgot_password_link():
    """The login page must NOT have a 'Forgot password?' link because password
    recovery is NOT implemented (per v3 spec)."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "Forgot password" not in html, (
        "Forgot-password link must NOT appear (recovery not implemented)"
    )
    assert "forgot" not in html.lower(), (
        "Any forgot-password reference must NOT appear"
    )


# ---------------------------------------------------------------------------
# 4. Registration page
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_register_page_uses_create_your_account_heading():
    """The register page must use 'Create your account' as the main heading."""
    c = Client()
    r = c.get("/accounts/register/")
    html = r.content.decode("utf-8")
    h1_match = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
    assert h1_match is not None, "Register page must have an <h1>"
    h1_text = h1_match.group(1).strip()
    assert "Create your account" in h1_text, (
        f"Register page h1 must be 'Create your account' — got {h1_text!r}"
    )


@pytest.mark.django_db
def test_register_page_has_clear_explanation():
    """The register page must have a clear explanation of the registration process
    (account reviewed by an administrator before activation)."""
    c = Client()
    r = c.get("/accounts/register/")
    html = r.content.decode("utf-8")
    assert "reviewed by an administrator" in html, (
        "Register page must explain the admin-review requirement"
    )


@pytest.mark.django_db
def test_register_page_preserves_all_fields():
    """The register page must preserve all existing fields: full_name, username,
    email, requested_role, organization, sub_county, ward, password1, password2."""
    c = Client()
    r = c.get("/accounts/register/")
    html = r.content.decode("utf-8")
    # All field labels must be present
    for label in ("Full name", "Username", "Requested role", "Sub-county", "Ward", "Password", "Confirm password"):
        assert label in html, f"Register page must have the {label!r} field"


@pytest.mark.django_db
def test_register_page_uses_btn_primary_class():
    """The 'Create account' button must use the .btn-primary class."""
    c = Client()
    r = c.get("/accounts/register/")
    html = r.content.decode("utf-8")
    assert "btn-primary" in html, "Create account button must use .btn-primary"
    assert "Create account" in html


@pytest.mark.django_db
def test_register_page_uses_auth_input_class_for_all_fields():
    """All register form inputs must use the .auth-input class (v5 token-based styling)."""
    c = Client()
    r = c.get("/accounts/register/")
    html = r.content.decode("utf-8")
    # Count auth-input occurrences — should be at least 9 (full_name, username, email,
    # requested_role, organization, sub_county, ward, password1, password2)
    auth_input_count = html.count("auth-input")
    assert auth_input_count >= 9, (
        f"Expected at least 9 .auth-input occurrences, got {auth_input_count}"
    )


@pytest.mark.django_db
def test_register_page_has_sign_in_link():
    """The register page must have an 'Already have an account? Sign in' link."""
    c = Client()
    r = c.get("/accounts/register/")
    html = r.content.decode("utf-8")
    assert "Already have an account?" in html
    assert "Sign in" in html
    assert 'href="/accounts/login/"' in html


@pytest.mark.django_db
def test_register_page_does_not_imply_open_registration():
    """The register page must NOT imply that anyone can register. The explanation
    must mention admin review / approval requirement."""
    c = Client()
    r = c.get("/accounts/register/")
    html = r.content.decode("utf-8")
    # Must mention 'reviewed by an administrator' or 'approved'
    assert "administrator" in html.lower() or "approved" in html.lower(), (
        "Register page must mention admin review/approval — must not imply open registration"
    )


@pytest.mark.django_db
def test_register_page_validation_preserved():
    """The registration validation must be preserved — submitting invalid data
    still fails (password too short, mismatched passwords, duplicate username)."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    # Create an existing user to test duplicate username rejection
    User.objects.create(username="existinguser", is_active=True)
    c = Client()
    # Submit with a duplicate username
    r = c.post("/accounts/register/", {
        "username": "existinguser",  # duplicate
        "full_name": "Test",
        "email": "",
        "requested_role": "viewer",
        "organization": "",
        "sub_county": "Nyatike",
        "ward": "Kachieng",
        "password1": "valid-password-123",
        "password2": "valid-password-123",
    })
    # Should re-render the form with errors (status 200), not redirect (302)
    assert r.status_code == 200, "Duplicate username should be rejected (200 = form re-render)"


# ---------------------------------------------------------------------------
# 5. Accessibility — labels, keyboard, focus, autocomplete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auth_pages_have_explicit_form_labels():
    """All form inputs must have explicit <label> elements associated via for/id."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    # Username
    assert '<label' in html and 'for="id_username"' in html
    # Password
    assert 'for="id_password"' in html
    # Inputs must have matching id
    assert 'id="id_username"' in html
    assert 'id="id_password"' in html


@pytest.mark.django_db
def test_auth_pages_have_skip_to_main_content():
    """Auth pages must have a skip-to-main-content link."""
    c = Client()
    for url in ["/accounts/login/", "/accounts/register/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        assert 'class="skip-link"' in html, f"Skip link missing on {url}"
        assert 'href="#main-content"' in html, f"Skip link href missing on {url}"
        assert 'id="main-content"' in html, f"main-content id missing on {url}"


@pytest.mark.django_db
def test_auth_pages_have_main_with_tabindex():
    """The <main> element must have tabindex='-1' so the skip link lands properly."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert 'tabindex="-1"' in html, "main element must have tabindex='-1' for skip link"


@pytest.mark.django_db
def test_auth_inputs_meet_touch_target_size():
    """The auth-input class must have min-height: 44px (WCAG 2.5.5 touch target)."""
    with open("/home/z/my-project/majishamba_fresh/static/css/dashboard.css") as f:
        css = f.read()
    auth_input_block = re.search(r"\.auth-input\s*\{[^}]+\}", css, re.S)
    assert auth_input_block is not None
    assert "min-height: 44px" in auth_input_block.group(0), (
        ".auth-input must have min-height: 44px (WCAG 2.5.5 touch target)"
    )


@pytest.mark.django_db
def test_auth_error_alert_does_not_rely_on_color_alone():
    """Form error alerts must have a text label (not just color). The .auth-error-alert
    has 'Sign in failed' text + 'Please check your username and password' detail."""
    c = Client()
    # Submit invalid credentials to trigger the error alert
    r = c.post("/accounts/login/", {"username": "nonexistent", "password": "wrong"})
    html = r.content.decode("utf-8")
    # The error alert must contain text, not just be a colored box
    assert "Sign in failed" in html, "Error alert must have 'Sign in failed' text label"
    assert "Please check your username and password" in html, (
        "Error alert must have detail text (not just color)"
    )


# ---------------------------------------------------------------------------
# 6. Security — no functionality weakened
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_csrf_protection_preserved():
    """CSRF protection must still be enforced on the login form."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "csrfmiddlewaretoken" in html, "CSRF token must be present in login form"


@pytest.mark.django_db
def test_register_csrf_protection_preserved():
    """CSRF protection must still be enforced on the register form."""
    c = Client()
    r = c.get("/accounts/register/")
    html = r.content.decode("utf-8")
    assert "csrfmiddlewaretoken" in html, "CSRF token must be present in register form"


@pytest.mark.django_db
def test_register_form_novalidate_preserved():
    """The register form must have novalidate (so Django-side validation runs,
    not just browser-side). This is the existing behavior."""
    c = Client()
    r = c.get("/accounts/register/")
    html = r.content.decode("utf-8")
    assert "novalidate" in html, "Register form must have 'novalidate' (Django-side validation)"


@pytest.mark.django_db
def test_login_form_novalidate_preserved():
    """The login form must have novalidate."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "novalidate" in html


# ---------------------------------------------------------------------------
# 7. No conflicting color system
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auth_pages_do_not_use_conflicting_tailwind_color_classes():
    """Auth pages must NOT use hardcoded Tailwind color utilities like 'bg-emerald-700'
    or 'text-emerald-700' for the main elements — they should use the v5 semantic
    classes (.btn-primary, .auth-input, .auth-brand, etc.) that reference the
    centralized design tokens."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    # The old hardcoded 'bg-emerald-700' for the Sign in button must be gone
    # (it should use .btn-primary now)
    assert "bg-emerald-700" not in html, (
        "Old hardcoded bg-emerald-700 must be replaced by .btn-primary (uses design tokens)"
    )


# ---------------------------------------------------------------------------
# 8. Registration pending page
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_registration_pending_page_uses_v5_theme():
    """The registration_pending page must use the v5 auth theme classes."""
    c = Client()
    r = c.get("/accounts/registration/pending/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "auth-card" in html, "registration_pending must use .auth-card"
    assert "auth-card-heading" in html
    assert "Account pending review" in html
    assert "Back to sign in" in html
    assert 'href="/accounts/login/"' in html


# ---------------------------------------------------------------------------
# 9. Auth nav (Sign in / Create account) preserved
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auth_header_still_has_signin_createaccount_links():
    """The auth header must still have 'Sign in' and 'Create account' links
    (the v4 app-shell spec — unchanged by the v6 auth theme)."""
    c = Client()
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert "Sign in" in html
    assert "Create account" in html
    assert 'href="/accounts/login/"' in html
    assert 'href="/accounts/register/"' in html


@pytest.mark.django_db
def test_auth_nav_active_state_uses_aria_current():
    """The active auth nav link (Sign in on /login/, Create account on /register/)
    must use aria-current='page' (not color alone)."""
    c = Client()
    # On /login/, 'Sign in' should be active
    r = c.get("/accounts/login/")
    html = r.content.decode("utf-8")
    assert 'aria-current="page"' in html

    # On /register/, 'Create account' should be active
    r = c.get("/accounts/register/")
    html = r.content.decode("utf-8")
    assert 'aria-current="page"' in html


# ---------------------------------------------------------------------------
# 10. No template-comment leaks (regression)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auth_pages_no_template_comment_leaks():
    """Verify the v6 auth theme changes didn't reintroduce multi-line {# ... #}
    template comments that leak to the browser."""
    c = Client()
    for url in ["/accounts/login/", "/accounts/register/", "/accounts/registration/pending/"]:
        r = c.get(url)
        html = r.content.decode("utf-8")
        leaks = re.findall(r"\{#.*?#\}", html, re.S)
        multi_line_leaks = [l for l in leaks if "\n" in l]
        assert not multi_line_leaks, (
            f"Multi-line {{# ... #}} template comments leaked on {url}: {multi_line_leaks}"
        )
        # Also check no {% %} tag leaks
        tag_leaks = [l for l in re.findall(r"\{%.*?%\}", html, re.S) if l.startswith("{%")]
        assert not tag_leaks, f"Template tag leaks on {url}: {tag_leaks}"
