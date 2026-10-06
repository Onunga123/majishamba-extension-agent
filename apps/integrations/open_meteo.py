"""Open-Meteo Forecast API adapter — automated structured weather ingestion.

Provider: Open-Meteo (https://open-meteo.com/)
Product: Forecast API v1 — daily forecast, up to 16 days
Licence: CC-BY 4.0 (free for non-commercial use, no API key required)
Limits: 10,000 calls/day, 5,000/hour, 600/minute
Attribution: "Forecast from Open-Meteo (CC-BY 4.0)"

This adapter:
1. Fetches structured JSON from the Open-Meteo API
2. Validates the response schema
3. Stores a WeatherSignal with full provenance
4. Is idempotent (re-fetching updates the same record by location+date)
5. Never sets onset_confirmed (forecasts don't prove onset)
6. Never converts qualitative text to numeric rainfall
7. Distinguishes forecast precipitation from historical/observation data

Usage:
    python manage.py refresh_weather  # fetch for all approved locality coords
    python manage.py refresh_weather --dry-run  # preview without writing

Configuration (env vars):
    WEATHER_PROVIDER=open_meteo (default)
    OPEN_METEO_ENDPOINT=https://api.open-meteo.com/v1/forecast
    WEATHER_REFRESH_HOURS=6 (refresh interval; stale after this)
    WEATHER_REQUEST_TIMEOUT=30 (HTTP timeout in seconds)
    WEATHER_DAILY_BUDGET=100 (max API calls per day)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("majishamba.integrations.open_meteo")


OPEN_METEO_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ATTRIBUTION = "Forecast from Open-Meteo (CC-BY 4.0)"
OPEN_METEO_LICENCE = "CC-BY 4.0 — free for non-commercial use"
OPEN_METEO_FORECAST_DAYS = 7  # 7-day forecast (reliable range)

# WMO weather codes → short descriptions (for the forecast_summary field)
WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def fetch_open_meteo_forecast(
    *,
    latitude: float,
    longitude: float,
    forecast_days: int = OPEN_METEO_FORECAST_DAYS,
    timeout: int = 30,
) -> dict[str, Any] | None:
    """Fetch a structured 7-day forecast from the Open-Meteo API.

    Returns a validated dict with daily forecast data, or None on failure.
    Never raises — logs errors and returns None.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "precipitation_sum,precipitation_probability_max,temperature_2m_max,temperature_2m_min,weathercode,windspeed_10m_max,relative_humidity_2m_max",
        "timezone": "Africa/Nairobi",
        "forecast_days": forecast_days,
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(OPEN_METEO_ENDPOINT, params=params)
            if resp.status_code != 200:
                logger.warning("Open-Meteo API returned HTTP %s", resp.status_code)
                return None
            data = resp.json()
            # Validate schema
            if "daily" not in data or "time" not in data["daily"]:
                logger.warning("Open-Meteo response missing 'daily.time' field")
                return None
            if len(data["daily"].get("time", [])) == 0:
                logger.warning("Open-Meteo response has empty forecast array")
                return None
            return data
    except Exception as exc:
        logger.warning("Open-Meteo fetch failed: %s", exc)
        return None


def parse_open_meteo_response(
    data: dict[str, Any],
    *,
    latitude: float,
    longitude: float,
) -> list[dict[str, Any]]:
    """Parse an Open-Meteo response into a list of daily forecast dicts.

    Each dict has:
    - date (ISO 8601)
    - precipitation_mm (float or None — null means unavailable, not zero)
    - precipitation_probability_pct (int or None)
    - temp_max_c (float or None)
    - temp_min_c (float or None)
    - weathercode (int or None)
    - weather_description (str)
    - windspeed_max_kmh (float or None)
    - humidity_max_pct (float or None)
    """
    daily = data.get("daily", {})
    times = daily.get("time", [])
    results: list[dict[str, Any]] = []
    for i, date_str in enumerate(times):
        precip = _safe_float(daily.get("precipitation_sum", [None])[i])
        prob = _safe_float(daily.get("precipitation_probability_max", [None])[i])
        tmax = _safe_float(daily.get("temperature_2m_max", [None])[i])
        tmin = _safe_float(daily.get("temperature_2m_min", [None])[i])
        wcode = _safe_int(daily.get("weathercode", [None])[i])
        wspeed = _safe_float(daily.get("windspeed_10m_max", [None])[i])
        humid = _safe_float(daily.get("relative_humidity_2m_max", [None])[i])

        # Build a qualitative forecast summary from the WMO code
        wmo_desc = WMO_CODES.get(wcode, "Unknown conditions") if wcode is not None else "Unknown conditions"
        summary_parts = [wmo_desc]
        if precip is not None and precip > 0:
            summary_parts.append(f"Precipitation: {precip} mm")
        if prob is not None:
            summary_parts.append(f"Probability: {prob}%")
        if tmax is not None and tmin is not None:
            summary_parts.append(f"Temp: {tmin}–{tmax} °C")
        if wspeed is not None:
            summary_parts.append(f"Wind: {wspeed} km/h")

        results.append({
            "date": date_str,
            "precipitation_mm": precip,
            "precipitation_probability_pct": prob,
            "temp_max_c": tmax,
            "temp_min_c": tmin,
            "weathercode": wcode,
            "weather_description": wmo_desc,
            "windspeed_max_kmh": wspeed,
            "humidity_max_pct": humid,
            "forecast_summary": ". ".join(summary_parts) + ".",
        })
    return results


def ingest_open_meteo_forecast(
    *,
    latitude: float,
    longitude: float,
    locality_name: str = "",
    cluster_id: str = "",
    actor_id: int | None = None,
) -> dict[str, Any]:
    """Fetch and store a 7-day Open-Meteo forecast for the given coordinates.

    Stores ONE WeatherSignal per forecast day. Idempotent: re-fetching
    updates the existing records by (latitude, longitude, date).

    Returns a dict with:
    - success: bool
    - weather_signal_ids: list of created/updated signal IDs
    - provider: "open_meteo"
    - product: "7-day forecast"
    - location: "lat, lon"
    - errors: list of error messages
    """
    from apps.weather.models import WeatherSignal
    from apps.audit.service import log_audit_event

    raw = fetch_open_meteo_forecast(latitude=latitude, longitude=longitude)
    if raw is None:
        return {
            "success": False,
            "weather_signal_ids": [],
            "provider": "open_meteo",
            "product": "7-day forecast",
            "location": f"{latitude}, {longitude}",
            "errors": ["Open-Meteo API fetch failed (see logs)"],
        }

    # Compute a checksum of the raw response for provenance
    raw_json = json.dumps(raw, sort_keys=True, default=str)
    checksum = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()[:16]

    # Get the actual returned coordinates (may differ from requested)
    returned_lat = raw.get("latitude", latitude)
    returned_lon = raw.get("longitude", longitude)
    elevation = raw.get("elevation")

    daily_forecasts = parse_open_meteo_response(raw, latitude=latitude, longitude=longitude)
    signal_ids: list[int] = []
    first_date = daily_forecasts[0]["date"] if daily_forecasts else ""
    last_date = daily_forecasts[-1]["date"] if daily_forecasts else ""

    for fc in daily_forecasts:
        fc_date = dt.date.fromisoformat(fc["date"])
        # Build the forecast_summary from structured fields
        summary = fc["forecast_summary"]

        # Create or update the WeatherSignal (idempotent by area_label + period + publication_date)
        area_label = f"Open-Meteo {locality_name or 'Kachieng area'} ({returned_lat:.4f}, {returned_lon:.4f})"

        # Check for existing record (same area_label, same date)
        existing = WeatherSignal.objects.filter(
            area_label=area_label,
            period="7_day_forecast",
            publication_date=fc_date,
        ).first()

        if existing:
            # Update the existing record
            existing.forecast_summary = summary
            existing.rainfall_mm = fc["precipitation_mm"]
            existing.rainfall_period_note = f"Daily precipitation forecast for {fc_date}"
            existing.onset_status = "unknown"  # NEVER set onset_confirmed from a forecast
            existing.confidence = "medium"
            existing.source_authority = "Open-Meteo"
            existing.product_type = "7-day forecast (Open-Meteo)"
            existing.source_url = f"https://open-meteo.com/en/docs?lat={latitude}&lon={longitude}"
            existing.licence_or_permission_basis = OPEN_METEO_LICENCE
            existing.permission_status = WeatherSignal.PermissionStatus.OPEN_DATA
            existing.synthetic_flag = WeatherSignal.SyntheticFlag.REAL
            existing.verification_status = WeatherSignal.VerificationStatus.CURRENT_OFFICIAL
            existing.extraction_review_status = WeatherSignal.ExtractionReviewStatus.METADATA_ONLY
            existing.raw_document_checksum = checksum
            existing.last_checked_at = dt.datetime.now(dt.timezone.utc)
            existing.save()
            signal_ids.append(existing.id)
        else:
            sig = WeatherSignal.objects.create(
                area_label=area_label,
                period="7_day_forecast",
                rainfall_mm=fc["precipitation_mm"],
                rainfall_units="mm",
                rainfall_period_note=f"Daily precipitation forecast for {fc_date}",
                forecast_summary=summary,
                onset_status="unknown",  # NEVER set onset_confirmed from a forecast
                confidence="medium",
                source_authority="Open-Meteo",
                product_type="7-day forecast (Open-Meteo)",
                publication_date=fc_date,
                valid_from=fc_date,
                valid_to=fc_date,
                geographic_scope=locality_name or "Kachieng area",
                coverage_level="point",
                source_url=f"https://open-meteo.com/en/docs?lat={latitude}&lon={longitude}",
                source=f"Open-Meteo 7-day forecast ({returned_lat:.4f}, {returned_lon:.4f})",
                source_date=fc_date,
                licence_or_permission_basis=OPEN_METEO_LICENCE,
                permission_status=WeatherSignal.PermissionStatus.OPEN_DATA,
                synthetic_flag=WeatherSignal.SyntheticFlag.REAL,
                verification_status=WeatherSignal.VerificationStatus.CURRENT_OFFICIAL,
                extraction_review_status=WeatherSignal.ExtractionReviewStatus.METADATA_ONLY,
                raw_document_checksum=checksum,
                last_checked_at=dt.datetime.now(dt.timezone.utc),
            )
            signal_ids.append(sig.id)

    log_audit_event(
        actor_id=actor_id,
        action="ingest:open_meteo_forecast",
        metadata={
            "provider": "open_meteo",
            "latitude": returned_lat,
            "longitude": returned_lon,
            "elevation": elevation,
            "locality": locality_name,
            "cluster_id": cluster_id,
            "forecast_days": len(daily_forecasts),
            "first_date": first_date,
            "last_date": last_date,
            "checksum": checksum,
        },
    )

    return {
        "success": True,
        "weather_signal_ids": signal_ids,
        "provider": "open_meteo",
        "product": "7-day forecast",
        "location": f"{returned_lat:.4f}, {returned_lon:.4f}",
        "elevation": elevation,
        "forecast_days": len(daily_forecasts),
        "first_date": first_date,
        "last_date": last_date,
        "errors": [],
    }


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
