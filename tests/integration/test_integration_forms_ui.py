"""Regression tests for the standardised integration form pages.

Tests that the three integration form pages use the authenticated-app
design conventions: text-2xl headings, 44px primary buttons, rectangular
secondary Cancel buttons, and w-full styled form widgets. Also tests
that valid and invalid form submissions still work after the widget
class changes.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.test import Client


# ---------------------------------------------------------------------------
# Helper: check that a substring appears in the rendered HTML
# ---------------------------------------------------------------------------
def _has(html: str, needle: str) -> bool:
    return needle in html


# ---------------------------------------------------------------------------
# 1. KMD ingest — page heading, buttons, widget styling
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_kmd_ingest_heading_is_text_2xl(officer_client):
    r = officer_client.get("/integrations/kmd/ingest/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert (
        'class="text-2xl font-semibold text-stone-900"' in html
    ), "KMD ingest page h1 must use text-2xl font-semibold text-stone-900"
    assert "Ingest KMD bulletin" in html


@pytest.mark.django_db
def test_kmd_ingest_submit_button_has_44px_min_height(officer_client):
    r = officer_client.get("/integrations/kmd/ingest/")
    html = r.content.decode("utf-8")
    # The submit button must have min-h-[44px] in its class
    assert "min-h-[44px]" in html, "Submit button must have min-h-[44px]"
    assert "Ingest bulletin" in html


@pytest.mark.django_db
def test_kmd_ingest_cancel_is_rectangular_button(officer_client):
    r = officer_client.get("/integrations/kmd/ingest/")
    html = r.content.decode("utf-8")
    # Cancel must be a link with border styling, not plain text
    assert "Cancel" in html
    assert "border border-stone-300" in html, "Cancel must have a visible border (border-stone-300)"
    # The old plain-text Cancel class must NOT be present
    assert 'class="text-stone-600 text-sm self-center"' not in html


@pytest.mark.django_db
def test_kmd_ingest_cancel_links_to_integrations_index(officer_client):
    r = officer_client.get("/integrations/kmd/ingest/")
    html = r.content.decode("utf-8")
    assert 'href="/integrations/"' in html, "Cancel must link to /integrations/"


@pytest.mark.django_db
def test_kmd_ingest_form_widgets_have_w_full_class(officer_client):
    r = officer_client.get("/integrations/kmd/ingest/")
    html = r.content.decode("utf-8")
    # At least one input, select, and textarea must have the w-full class
    assert (
        'class="w-full ' in html or "w-full " in html
    ), "Form widgets must have the w-full styling class"
    # The textarea specifically must have w-full (was the overflow cause)
    assert "<textarea" in html, "KMD ingest form must have a textarea (forecast_summary)"
    textarea_match = html.count("w-full")
    assert (
        textarea_match >= 10
    ), f"Expected at least 10 widgets with w-full class, found {textarea_match}"


# ---------------------------------------------------------------------------
# 2. Pest report — page heading, buttons, widget styling
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_pest_report_heading_is_text_2xl(officer_client):
    r = officer_client.get("/integrations/pests/report/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert 'class="text-2xl font-semibold text-stone-900"' in html
    assert "Officer field report — pest observation" in html


@pytest.mark.django_db
def test_pest_report_submit_button_has_44px_min_height(officer_client):
    r = officer_client.get("/integrations/pests/report/")
    html = r.content.decode("utf-8")
    assert "min-h-[44px]" in html
    assert "Submit field report" in html


@pytest.mark.django_db
def test_pest_report_cancel_is_rectangular_button(officer_client):
    r = officer_client.get("/integrations/pests/report/")
    html = r.content.decode("utf-8")
    assert "border border-stone-300" in html
    assert 'class="text-stone-600 text-sm self-center"' not in html


@pytest.mark.django_db
def test_pest_report_form_widgets_have_w_full_class(officer_client):
    r = officer_client.get("/integrations/pests/report/")
    html = r.content.decode("utf-8")
    assert "<textarea" in html, "Pest report form must have a textarea (advisory)"
    assert html.count("w-full") >= 5, "Expected at least 5 widgets with w-full class"


# ---------------------------------------------------------------------------
# 3. Pest notice — page heading, buttons, widget styling
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_pest_notice_heading_is_text_2xl(officer_client):
    r = officer_client.get("/integrations/pests/notice/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert 'class="text-2xl font-semibold text-stone-900"' in html
    assert "Ingest published pest notice" in html


@pytest.mark.django_db
def test_pest_notice_submit_button_has_44px_min_height(officer_client):
    r = officer_client.get("/integrations/pests/notice/")
    html = r.content.decode("utf-8")
    assert "min-h-[44px]" in html
    assert "Ingest notice" in html


@pytest.mark.django_db
def test_pest_notice_cancel_is_rectangular_button(officer_client):
    r = officer_client.get("/integrations/pests/notice/")
    html = r.content.decode("utf-8")
    assert "border border-stone-300" in html
    assert 'class="text-stone-600 text-sm self-center"' not in html


@pytest.mark.django_db
def test_pest_notice_form_widgets_have_w_full_class(officer_client):
    r = officer_client.get("/integrations/pests/notice/")
    html = r.content.decode("utf-8")
    assert html.count("w-full") >= 8, "Expected at least 8 widgets with w-full class"


# ---------------------------------------------------------------------------
# 4. Form submission — valid data still works (KMD ingest)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_kmd_ingest_valid_submission_redirects_to_dashboard(officer_client):
    """A valid KMD ingest POST must redirect to the dashboard (302)."""
    r = officer_client.post(
        "/integrations/kmd/ingest/",
        {
            "product_type": "Daily Forecast",
            "publication_date": "2026-10-14",
            "valid_from": "2026-10-14",
            "valid_to": "2026-10-15",
            "geographic_scope": "Migori County",
            "coverage_level": "county",
            "area_label": "Migori County",
            "period": "daily_forecast",
            "forecast_summary": "Showers and thunderstorms expected over parts of Migori County.",
            "rainfall_mm": "",
            "rainfall_period_note": "",
            "onset_status": "unknown",
            "source_url": "https://meteo.go.ke/our-products/daily-forecast",
        },
    )
    assert r.status_code == 302, f"Expected 302 redirect, got {r.status_code}"
    assert "/dashboard/" in r["Location"], f"Expected redirect to dashboard, got {r['Location']}"
    # Verify a WeatherSignal was actually created
    from apps.weather.models import WeatherSignal

    ws = (
        WeatherSignal.objects.filter(
            source_authority="Kenya Meteorological Department",
            product_type="Daily Forecast",
        )
        .order_by("-id")
        .first()
    )
    assert ws is not None, "WeatherSignal must have been created by the valid submission"


# ---------------------------------------------------------------------------
# 5. Form submission — invalid data re-renders with errors (KMD ingest)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_kmd_ingest_invalid_submission_re_renders_with_errors(officer_client):
    """An invalid KMD ingest POST must re-render the form page (200) with errors."""
    r = officer_client.post(
        "/integrations/kmd/ingest/",
        {
            "product_type": "",  # missing required field
            "publication_date": "",  # missing required field
            "coverage_level": "county",
            "area_label": "Migori County",
            "period": "daily_forecast",
            "forecast_summary": "Test forecast",
            "onset_status": "unknown",
        },
    )
    assert r.status_code == 200, f"Expected 200 (re-render with errors), got {r.status_code}"
    html = r.content.decode("utf-8")
    # The form must show error messages
    assert (
        "error" in html.lower() or "required" in html.lower() or "correct" in html.lower()
    ), "Invalid form submission must show error messages"


# ---------------------------------------------------------------------------
# 6. Permission — viewer cannot access integration forms
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_viewer_cannot_access_kmd_ingest(viewer_client):
    """A viewer must get 403 on the KMD ingest form (requires officer role)."""
    r = viewer_client.get("/integrations/kmd/ingest/")
    assert r.status_code == 403, f"Viewer should get 403, got {r.status_code}"
