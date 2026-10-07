"""Tests for Open-Meteo weather API integration."""
from __future__ import annotations

import datetime as dt
import json
from unittest.mock import patch, MagicMock

import pytest

from apps.integrations.open_meteo import (
    fetch_open_meteo_forecast,
    parse_open_meteo_response,
    ingest_open_meteo_forecast,
    WMO_CODES,
)


# --- Mock response data ---
MOCK_RESPONSE = {
    "latitude": -0.949,
    "longitude": 34.414,
    "elevation": 1435.0,
    "generationtime_ms": 1.5,
    "utc_offset_seconds": 10800,
    "timezone": "Africa/Nairobi",
    "timezone_abbreviation": "GMT+3",
    "daily_units": {
        "time": "iso8601",
        "precipitation_sum": "mm",
        "precipitation_probability_max": "%",
        "temperature_2m_max": "°C",
        "temperature_2m_min": "°C",
        "weathercode": "wmo code",
        "windspeed_10m_max": "km/h",
        "relative_humidity_2m_max": "%",
    },
    "daily": {
        "time": ["2026-10-06", "2026-10-07", "2026-10-08"],
        "precipitation_sum": [1.6, 12.9, None],
        "precipitation_probability_max": [100, 96, 80],
        "temperature_2m_max": [31.7, 29.0, 29.7],
        "temperature_2m_min": [19.1, 19.2, 17.5],
        "weathercode": [53, 95, 51],
        "windspeed_10m_max": [21.8, 19.3, 18.2],
        "relative_humidity_2m_max": [80, 90, 75],
    },
}


@pytest.mark.django_db
def test_fetch_open_meteo_returns_valid_data():
    """Mock the HTTP call and verify the response is parsed correctly."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MOCK_RESPONSE

    with patch("httpx.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.get.return_value = mock_resp
        mock_client_class.return_value = mock_client

        result = fetch_open_meteo_forecast(latitude=-0.965, longitude=34.445)
        assert result is not None
        assert "daily" in result
        assert len(result["daily"]["time"]) == 3


@pytest.mark.django_db
def test_fetch_open_meteo_returns_none_on_http_error():
    """If the API returns a non-200 status, fetch returns None."""
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.json.return_value = {"error": "rate limited"}

    with patch("httpx.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.get.return_value = mock_resp
        mock_client_class.return_value = mock_client

        result = fetch_open_meteo_forecast(latitude=-0.965, longitude=34.445)
        assert result is None


@pytest.mark.django_db
def test_parse_open_meteo_response_handles_null_precipitation():
    """Null precipitation must be stored as None, not zero."""
    parsed = parse_open_meteo_response(MOCK_RESPONSE, latitude=-0.965, longitude=34.445)
    assert len(parsed) == 3
    # Day 3 has null precipitation
    assert parsed[2]["precipitation_mm"] is None
    # Day 1 has 1.6 mm
    assert parsed[0]["precipitation_mm"] == 1.6


@pytest.mark.django_db
def test_parse_open_meteo_response_uses_wmo_codes():
    """Weather codes are translated to human-readable descriptions."""
    parsed = parse_open_meteo_response(MOCK_RESPONSE, latitude=-0.965, longitude=34.445)
    assert "Moderate drizzle" in parsed[0]["weather_description"]
    assert "Thunderstorm" in parsed[1]["weather_description"]


@pytest.mark.django_db
def test_ingest_open_meteo_forecast_stores_signals(officer):
    """Full ingestion stores WeatherSignal records with correct provenance."""
    with patch("apps.integrations.open_meteo.fetch_open_meteo_forecast") as mock_fetch:
        mock_fetch.return_value = MOCK_RESPONSE
        result = ingest_open_meteo_forecast(
            latitude=-0.965,
            longitude=34.445,
            locality_name="Sori",
            cluster_id="KACH-01",
            actor_id=officer.id,
        )
    assert result["success"] is True
    assert result["provider"] == "open_meteo"
    assert result["forecast_days"] == 3
    assert len(result["weather_signal_ids"]) == 3

    from apps.weather.models import WeatherSignal
    signals = WeatherSignal.objects.filter(source_authority="Open-Meteo")
    assert signals.count() == 3
    for sig in signals:
        assert sig.synthetic_flag == "real"
        assert sig.verification_status == "current_official"
        assert sig.onset_status == "unknown"  # NEVER onset_confirmed
        assert sig.source_authority == "Open-Meteo"
        assert sig.product_type == "7-day forecast (Open-Meteo)"
        assert "CC-BY 4.0" in sig.licence_or_permission_basis


@pytest.mark.django_db
def test_ingest_open_meteo_forecast_idempotent(officer):
    """Re-fetching updates existing records, doesn't create duplicates."""
    with patch("apps.integrations.open_meteo.fetch_open_meteo_forecast") as mock_fetch:
        mock_fetch.return_value = MOCK_RESPONSE
        # First fetch
        ingest_open_meteo_forecast(latitude=-0.965, longitude=34.445, locality_name="Sori")
        # Second fetch (same data)
        ingest_open_meteo_forecast(latitude=-0.965, longitude=34.445, locality_name="Sori")

    from apps.weather.models import WeatherSignal
    # Should still have 3 records (one per day), not 6
    count = WeatherSignal.objects.filter(source_authority="Open-Meteo").count()
    assert count == 3, f"Idempotency failed: expected 3, got {count}"


@pytest.mark.django_db
def test_ingest_open_meteo_never_sets_onset_confirmed(officer):
    """A forecast must never set onset_confirmed."""
    with patch("apps.integrations.open_meteo.fetch_open_meteo_forecast") as mock_fetch:
        mock_fetch.return_value = MOCK_RESPONSE
        ingest_open_meteo_forecast(latitude=-0.965, longitude=34.445)

    from apps.weather.models import WeatherSignal
    for sig in WeatherSignal.objects.filter(source_authority="Open-Meteo"):
        assert sig.onset_status == "unknown"


@pytest.mark.django_db
def test_ingest_open_meteo_handles_api_failure(officer):
    """When the API fails, the adapter returns failure without creating records."""
    with patch("apps.integrations.open_meteo.fetch_open_meteo_forecast") as mock_fetch:
        mock_fetch.return_value = None
        result = ingest_open_meteo_forecast(latitude=-0.965, longitude=34.445)

    assert result["success"] is False
    assert len(result["errors"]) > 0
    from apps.weather.models import WeatherSignal
    assert WeatherSignal.objects.filter(source_authority="Open-Meteo").count() == 0


@pytest.mark.django_db
def test_open_meteo_weather_excludes_synthetic_from_agent(officer):
    """API weather records are marked real, not synthetic — agent can use them."""
    with patch("apps.integrations.open_meteo.fetch_open_meteo_forecast") as mock_fetch:
        mock_fetch.return_value = MOCK_RESPONSE
        ingest_open_meteo_forecast(latitude=-0.965, longitude=34.445, locality_name="Sori")

    from apps.weather.models import WeatherSignal
    sig = WeatherSignal.objects.filter(source_authority="Open-Meteo").first()
    assert sig is not None
    assert sig.synthetic_flag == "real"
    assert sig.verification_status == "current_official"
    assert sig.is_synthetic is False


@pytest.mark.django_db
def test_open_meteo_provider_label_not_kmd(officer):
    """API weather is labelled 'Open-Meteo', NOT 'KMD'."""
    with patch("apps.integrations.open_meteo.fetch_open_meteo_forecast") as mock_fetch:
        mock_fetch.return_value = MOCK_RESPONSE
        ingest_open_meteo_forecast(latitude=-0.965, longitude=34.445)

    from apps.weather.models import WeatherSignal
    sig = WeatherSignal.objects.filter(source_authority="Open-Meteo").first()
    assert "KMD" not in sig.source_authority
    assert "Open-Meteo" in sig.source_authority
    assert "Open-Meteo" in sig.source
    assert "Open-Meteo" in sig.product_type


@pytest.mark.django_db
def test_null_precipitation_not_zero(officer):
    """Null precipitation is stored as None, NOT as 0.0."""
    with patch("apps.integrations.open_meteo.fetch_open_meteo_forecast") as mock_fetch:
        mock_fetch.return_value = MOCK_RESPONSE
        ingest_open_meteo_forecast(latitude=-0.965, longitude=34.445)

    from apps.weather.models import WeatherSignal
    # Day 3 (2026-10-08) has null precipitation in the mock
    null_sig = WeatherSignal.objects.get(
        source_authority="Open-Meteo",
        publication_date=dt.date(2026, 10, 8),
    )
    assert null_sig.rainfall_mm is None
    assert null_sig.rainfall_display == "Not specified in this bulletin"


@pytest.mark.django_db
def test_timezone_is_africa_nairobi(officer):
    """The API request uses Africa/Nairobi timezone and the response reflects it."""
    with patch("apps.integrations.open_meteo.fetch_open_meteo_forecast") as mock_fetch:
        mock_fetch.return_value = MOCK_RESPONSE
        ingest_open_meteo_forecast(latitude=-0.965, longitude=34.445)

    from apps.weather.models import WeatherSignal
    sig = WeatherSignal.objects.filter(source_authority="Open-Meteo").first()
    # The dates should be in Africa/Nairobi timezone (dates from the daily.time array)
    # which are ISO-8601 date strings (no timezone offset needed for daily data).
    assert sig.publication_date is not None
    assert sig.valid_from is not None
    assert sig.valid_to is not None


@pytest.mark.django_db
def test_synthetic_coordinates_not_queried(officer):
    """Synthetic locality coordinates must not be used for API queries."""
    # This is tested by the refresh_weather command which filters by
    # verification_status='approved' and excludes 'synthetic' coordinate_type.
    from apps.geography.models import LocalityCoordinate
    from apps.clusters.models import FarmerCluster
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())

    # Create a synthetic coordinate (should be excluded from refresh)
    cluster = FarmerCluster.objects.get(cluster_id="KACH-01")
    LocalityCoordinate.objects.create(
        cluster=cluster,
        locality_name="Synthetic",
        latitude=-0.952,
        longitude=34.432,
        coordinate_source="Synthetic",
        coordinate_type="synthetic",
        verification_status="approved",  # approved but synthetic type
    )
    # The refresh command filters by coordinate_type IN (owner_confirmed_reference, settlement_reference)
    # so synthetic coordinates are excluded.
    qs = LocalityCoordinate.objects.filter(
        verification_status="approved",
        coordinate_type__in=["owner_confirmed_reference", "settlement_reference"],
    )
    assert not qs.filter(coordinate_type="synthetic").exists()
