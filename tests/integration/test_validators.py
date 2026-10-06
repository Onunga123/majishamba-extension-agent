"""Tests for content validators — the 'eee' regression tests."""
from __future__ import annotations

import datetime as dt

import pytest

from apps.governance.validators import (
    validate_weather_content,
    validate_pest_content,
    is_meaningful_text,
)


# --- Weather content validation ---

@pytest.mark.django_db
def test_placeholder_text_eee_is_rejected():
    """Regression: 'eee' as forecast_summary must be rejected (the original bug)."""
    result = validate_weather_content(
        forecast_summary="eee",
        onset_status="unknown",
        rainfall_mm=None,
        rainfall_period_note="",
    )
    assert not result.is_valid
    assert any("placeholder text" in e.lower() or "too short" in e.lower() for e in result.errors)


@pytest.mark.django_db
def test_meaningful_forecast_is_accepted():
    """A real forecast summary is accepted."""
    result = validate_weather_content(
        forecast_summary="Showers and thunderstorms expected over parts of Migori County in the afternoon and night.",
        onset_status="unknown",
        rainfall_mm=None,
        rainfall_period_note="",
    )
    assert result.is_valid
    assert len(result.errors) == 0


@pytest.mark.django_db
def test_onset_confirmed_without_onset_keywords_rejected():
    """onset_confirmed is not accepted unless the forecast text mentions onset."""
    result = validate_weather_content(
        forecast_summary="Sunny intervals with cloudy conditions over the county.",
        onset_status="onset_confirmed",
        rainfall_mm=None,
        rainfall_period_note="",
    )
    assert not result.is_valid
    assert any("onset_confirmed" in e for e in result.errors)


@pytest.mark.django_db
def test_onset_confirmed_with_onset_keywords_accepted():
    """onset_confirmed IS accepted when the text mentions onset."""
    result = validate_weather_content(
        forecast_summary="The rains have started over Migori County. Onset confirmed. Farmers can begin planting.",
        onset_status="onset_confirmed",
        rainfall_mm=None,
        rainfall_period_note="",
    )
    assert result.is_valid


@pytest.mark.django_db
def test_onset_unknown_is_always_accepted():
    """onset_unknown is the safe default and always passes."""
    result = validate_weather_content(
        forecast_summary="Showers and thunderstorms expected over parts of Migori County.",
        onset_status="unknown",
        rainfall_mm=None,
        rainfall_period_note="",
    )
    assert result.is_valid


@pytest.mark.django_db
def test_zero_validity_window_warns():
    """A daily forecast where valid_from == valid_to == publication_date gets a warning."""
    d = dt.date(2026, 10, 6)
    result = validate_weather_content(
        forecast_summary="Showers and thunderstorms expected over parts of Migori County.",
        onset_status="unknown",
        rainfall_mm=None,
        rainfall_period_note="",
        valid_from=d,
        valid_to=d,
        publication_date=d,
    )
    assert result.is_valid  # warning, not error
    assert any("zero-day validity" in w.lower() or "same date" in w.lower() for w in result.warnings)


@pytest.mark.django_db
def test_whitespace_only_summary_rejected():
    """Whitespace-only forecast summary is rejected."""
    result = validate_weather_content(
        forecast_summary="   ",
        onset_status="unknown",
        rainfall_mm=None,
        rainfall_period_note="",
    )
    assert not result.is_valid


@pytest.mark.django_db
def test_rainfall_without_period_note_rejected():
    """Numeric rainfall without a period note is rejected."""
    result = validate_weather_content(
        forecast_summary="Heavy rainfall expected over Migori County in the next 24 hours.",
        onset_status="unknown",
        rainfall_mm=45.0,
        rainfall_period_note="",
    )
    assert not result.is_valid
    assert any("rainfall_period_note" in e for e in result.errors)


# --- Pest content validation ---

@pytest.mark.django_db
def test_pest_placeholder_rejected():
    result = validate_pest_content(
        pest="x",
        crop="maize",
        severity="not_specified",
        advisory="",
        coverage_level="ward",
    )
    assert not result.is_valid


@pytest.mark.django_db
def test_pest_high_severity_without_support_warns():
    result = validate_pest_content(
        pest="Fall Armyworm",
        crop="maize",
        severity="high",
        advisory="Some pest pressure observed.",
        coverage_level="ward",
    )
    assert result.is_valid  # warning, not error
    assert any("severity" in w.lower() for w in result.warnings)


@pytest.mark.django_db
def test_pest_high_severity_with_support_accepted():
    result = validate_pest_content(
        pest="Fall Armyworm",
        crop="maize",
        severity="high",
        advisory="High severity outbreak confirmed in three plots.",
        coverage_level="ward",
    )
    assert result.is_valid
    assert len(result.warnings) == 0


# --- is_meaningful_text helper ---

def test_is_meaningful_text_rejects_short():
    assert not is_meaningful_text("eee")
    assert not is_meaningful_text("test")
    assert not is_meaningful_text("n/a")
    assert not is_meaningful_text("")

def test_is_meaningful_text_accepts_real():
    assert is_meaningful_text("Showers and thunderstorms over Migori County")
    assert is_meaningful_text("Heavy rainfall expected in the afternoon")


# --- KMD adapter integration tests ---

@pytest.mark.django_db
def test_kmd_ingest_quarantines_eee_forecast(officer):
    """The KMD adapter must quarantine a record with forecast_summary='eee'."""
    from apps.integrations.kmd import ingest_kmd_bulletin_metadata
    result = ingest_kmd_bulletin_metadata(
        area_label="Migori County",
        period="daily_forecast",
        product_type="Daily Forecast",
        publication_date=dt.date(2026, 10, 6),
        coverage_level="county",
        forecast_summary="eee",
        onset_status="onset_confirmed",
        source_url="https://meteo.go.ke/our-products/daily-forecast",
    )
    assert not result["is_valid"]
    assert result["verification_status"] == "review_required"
    assert len(result["validation_errors"]) > 0
    # The quarantined record should NOT appear as "current_official" on the dashboard
    from apps.weather.models import WeatherSignal
    w = WeatherSignal.objects.get(id=result["weather_signal_id"])
    assert w.verification_status == "review_required"


@pytest.mark.django_db
def test_kmd_ingest_accepts_valid_forecast(officer):
    """The KMD adapter accepts a properly transcribed forecast."""
    from apps.integrations.kmd import ingest_kmd_bulletin_metadata
    result = ingest_kmd_bulletin_metadata(
        area_label="Migori County",
        period="daily_forecast",
        product_type="Daily Forecast",
        publication_date=dt.date(2026, 10, 6),
        valid_from=dt.date(2026, 10, 6),
        valid_to=dt.date(2026, 10, 7),
        coverage_level="county",
        forecast_summary="Showers and thunderstorms expected over parts of Migori County in the afternoon and night.",
        onset_status="unknown",
        source_url="https://meteo.go.ke/our-products/daily-forecast",
    )
    assert result["is_valid"]
    assert result["verification_status"] == "current_official"
    assert len(result["validation_errors"]) == 0


@pytest.mark.django_db
def test_dashboard_excludes_quarantined_weather(officer_client):
    """The dashboard must NOT show quarantined weather records as current."""
    from apps.integrations.kmd import ingest_kmd_bulletin_metadata
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    # Ingest a quarantined record
    ingest_kmd_bulletin_metadata(
        area_label="Migori County",
        period="daily_forecast",
        product_type="Daily Forecast",
        publication_date=dt.date(2026, 10, 6),
        coverage_level="county",
        forecast_summary="eee",
        onset_status="onset_confirmed",
    )
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The dashboard should show "No current verified KMD bulletin" (not the quarantined one)
    assert "No current verified KMD bulletin" in html
    # It should NOT show "eee" as a real forecast
    assert "eee" not in html
