"""Honest data-integration tests — verify synthetic is never relabelled as real,
and the dashboard shows honest availability states."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.management import call_command
from io import StringIO

from apps.calendars.models import CropCalendar
from apps.integrations.kalro import register_kalro_bibliographic_metadata, permission_status as kalro_status
from apps.integrations.kmd import (
    discover_kmd_products,
    ingest_kmd_bulletin_metadata,
    no_current_kmd_notice,
)
from apps.integrations.pests import (
    ingest_kalro_factsheet_metadata,
    ingest_officer_field_report,
    ingest_published_notice_metadata,
    no_current_pest_notice,
)
from apps.pests.models import PestAlert
from apps.weather.models import WeatherSignal


# --- WEATHER: KMD adapter ---------------------------------------------------

@pytest.mark.django_db
def test_kmd_product_catalogue_lists_real_products():
    """The KMD catalogue must list the products KMD actually publishes."""
    catalogue = discover_kmd_products()
    assert len(catalogue) >= 5
    product_names = [p["product_type"] for p in catalogue]
    assert "County Forecast" in product_names
    assert "7 Days Forecast" in product_names
    assert "Lake Victoria Fishing Forecast" in product_names
    # No fake products
    for p in catalogue:
        assert "synthetic" not in p["product_type"].lower()


@pytest.mark.django_db
def test_kmd_bulletin_ingest_marks_real_not_synthetic():
    """A KMD bulletin ingested via the adapter must be marked real, not synthetic."""
    res = ingest_kmd_bulletin_metadata(
        area_label="Migori County",
        period="7_day_forecast",
        product_type="7 Days Forecast",
        publication_date=dt.date(2026, 10, 5),
        valid_from=dt.date(2026, 10, 5),
        valid_to=dt.date(2026, 10, 12),
        geographic_scope="Migori County",
        coverage_level="county",
        forecast_summary="Showers and thunderstorms over parts of Migori.",
        rainfall_mm=None,  # bulletin does not specify a numeric value
        onset_status="unknown",
        source_url="https://meteo.go.ke/our-products/7-days-forecast",
    )
    sig = WeatherSignal.objects.get(id=res["weather_signal_id"])
    assert sig.synthetic_flag == "real"
    assert sig.verification_status == "current_official"
    assert sig.source_authority == "Kenya Meteorological Department"
    assert sig.rainfall_mm is None
    assert sig.rainfall_display == "Not specified in this bulletin"


@pytest.mark.django_db
def test_kmd_regional_forecast_marked_as_regional_context():
    """A Lake Victoria Basin forecast must be marked regional_context, not current_official."""
    res = ingest_kmd_bulletin_metadata(
        area_label="Lake Victoria Basin (covers Migori)",
        period="daily_forecast",
        product_type="Lake Victoria Fishing Forecast",
        publication_date=dt.date(2026, 10, 5),
        geographic_scope="Lake Victoria Basin",
        coverage_level="regional",
        forecast_summary="Wind and wave forecasts for the Lake Victoria Basin.",
        source_url="https://meteo.go.ke/our-products/",
    )
    sig = WeatherSignal.objects.get(id=res["weather_signal_id"])
    assert sig.verification_status == "regional_context"
    assert sig.is_regional_context


@pytest.mark.django_db
def test_kmd_rainfall_requires_period_note():
    """Numeric rainfall must record the period and geographic scope it applies to."""
    with pytest.raises(ValueError, match="rainfall_period_note is required"):
        ingest_kmd_bulletin_metadata(
            area_label="Migori County",
            period="7_day_forecast",
            product_type="7 Days Forecast",
            publication_date=dt.date(2026, 10, 5),
            geographic_scope="Migori County",
            coverage_level="county",
            rainfall_mm=25.0,  # numeric value provided without a period note
        )


@pytest.mark.django_db
def test_kmd_no_current_notice_default_is_honest():
    """The default KMD state must be 'no current notice' (NOT 'no rain' or 'zero rainfall')."""
    state = no_current_kmd_notice()
    assert state["state"] == "no_current_notice"
    assert "No current verified KMD bulletin" in state["message"]
    assert "manual retrieval" in state["manual_retrieval_note"].lower()
    # We never claim pests are absent or that there's no rainfall.
    assert "no pest risk" not in state.values()
    assert "zero rainfall" not in state.values()


# --- PESTS: officer field reports + published notices ---------------------

@pytest.mark.django_db
def test_officer_field_report_marked_correctly():
    """An officer field report must be labelled as officer_field_report, NOT as a KEPHIS/KALRO publication."""
    res = ingest_officer_field_report(
        officer_author_name="Jane Awuor",
        observation_date=dt.date(2026, 10, 5),
        coverage="Kachieng Ward",
        coverage_level="ward",
        pest="Fall Armyworm (Spodoptera frugiperda)",
        crop="maize",
        severity="not_specified",  # officer does not inflate
        advisory="Light fall armyworm pressure observed in three Kachieng plots.",
        actor_id=None,
    )
    alert = PestAlert.objects.get(id=res["pest_alert_id"])
    assert alert.synthetic_flag == "officer_report"
    assert alert.verification_status == "officer_field_report"
    assert alert.source_authority.startswith("Officer field report — Jane Awuor")
    assert alert.officer_author_name == "Jane Awuor"
    # Crucially: it must NOT be labelled as a KEPHIS/KALRO publication.
    assert "KEPHIS" not in alert.source_authority
    assert "KALRO" not in alert.source_authority


@pytest.mark.django_db
def test_published_notice_severity_kept_as_published():
    """Severity must be stored exactly as published. Do not inflate 'mentioned' to 'High'."""
    res = ingest_published_notice_metadata(
        authority="KEPHIS",
        product_type="Pest alert notice",
        publication_date=dt.date(2026, 10, 5),
        pest="Fall Armyworm (Spodoptera frugiperda)",
        crop="maize",
        severity="not_specified",  # source mentions the pest but does not state a severity
        geographic_scope="National (Kenya)",
        coverage_level="national",
        source_url="https://www.kephis.org/",
        source_document_id="KEPHIS-FAW-2026-10",
    )
    alert = PestAlert.objects.get(id=res["pest_alert_id"])
    assert alert.severity == "not_specified"
    assert alert.severity_display_safe == "Severity not stated in source"
    assert alert.verification_status == "current_official"


@pytest.mark.django_db
def test_kalro_factsheet_is_background_reference_not_outbreak():
    """A KALRO pest factsheet is BACKGROUND guidance, NOT a current outbreak."""
    res = ingest_kalro_factsheet_metadata(
        publication_date=dt.date(2024, 6, 1),
        pest="Fall Armyworm (Spodoptera frugiperda)",
        crop="maize",
        factsheet_url="https://keep.kalro.org/",
        factsheet_id="KALRO-FAW-FS-2024",
    )
    alert = PestAlert.objects.get(id=res["pest_alert_id"])
    assert alert.verification_status == "background_reference"
    assert alert.severity == "not_specified"
    assert alert.permission_status == "permission_pending"
    # No advisory text is extracted from the factsheet (KALRO © all rights reserved).
    assert alert.advisory == ""


@pytest.mark.django_db
def test_pest_no_current_notice_default_is_honest():
    """The default pest state must be 'no current verified notice' (NEVER 'No pest risk')."""
    state = no_current_pest_notice()
    assert state["state"] == "no_current_notice"
    assert "No current verified official pest notice" in state["message"]
    # Crucially: we explicitly say pests are NOT confirmed absent — the message
    # contains "does not establish that pests are absent", which is the honest
    # negation.
    assert "does not establish that pests are absent" in state["scouting_note"]
    assert "Local scouting and extension-officer verification remain necessary" in state["scouting_note"]
    # The `do_not_display` field documents what we must NEVER display to users.
    # It contains the literal string "No pest risk" — but as documentation of what
    # NOT to show, not as something we'd actually display. So we check that the
    # state's `message` and `scouting_note` (the user-facing fields) do NOT
    # claim "No pest risk".
    assert "No pest risk" not in state["message"]
    assert "No pest risk" not in state["scouting_note"]


# --- KALRO maize guidance: bibliographic metadata only --------------------

@pytest.mark.django_db
def test_kalro_bibliographic_metadata_has_no_extracted_dates_or_activities():
    """KALRO metadata must NOT include planting dates or activities (permission-pending)."""
    register_kalro_bibliographic_metadata()
    cc = CropCalendar.objects.get(crop="maize", zone_label="Migori-Low-Mid", season="short_rains")
    assert cc.permission_status == "permission_pending"
    assert cc.extraction_review_status == "not_extracted"
    assert cc.planting_window_start is None
    assert cc.planting_window_end is None
    assert cc.activities == []
    assert cc.source_authority == "KALRO"
    assert cc.product_type == "KCEP-CRAL Maize Extension Manual 2021 (national reference)"
    assert cc.coverage_level == "national"
    assert "permission pending" in cc.licence_or_permission_basis.lower()
    assert cc.planting_window_display == "Local planting dates not specified in this source"


@pytest.mark.django_db
def test_kalro_never_called_migori_calendar():
    """We never call a national manual a 'KALRO Migori short-rains calendar'."""
    state = kalro_status()
    assert state["do_not_label"] == "KALRO Migori short-rains calendar"
    register_kalro_bibliographic_metadata()
    cc = CropCalendar.objects.get(crop="maize", zone_label="Migori-Low-Mid", season="short_rains")
    assert "Migori short-rains calendar" not in cc.product_type
    assert "Migori short-rains calendar" not in cc.source


@pytest.mark.django_db
def test_kalro_is_stale_returns_false_for_reference_manuals():
    """Reference manuals do NOT auto-expire by date."""
    register_kalro_bibliographic_metadata()
    cc = CropCalendar.objects.get(crop="maize", zone_label="Migori-Low-Mid", season="short_rains")
    # Published 2021-04-01 — would be "stale" under the old 2-year rule, but
    # reference manuals are never stale by age alone.
    assert cc.is_stale() is False
    assert cc.is_stale(max_age_days=365 * 2) is True  # legacy caller can still get the old check


# --- DASHBOARD: honest states ---------------------------------------------

@pytest.mark.django_db
def test_dashboard_shows_no_current_kmd_notice_when_no_real_bulletin(officer_client):
    """When only synthetic weather fixtures are loaded, the dashboard must show
    the honest 'No current verified KMD bulletin' state, not the synthetic one
    as if it were a real KMD feed."""
    call_command("loaddata", "data/fixtures/migori_kachieng_clusters.json",
                 "data/fixtures/migori_kachieng_plots.json",
                 "data/fixtures/migori_crop_calendars.json",
                 "data/fixtures/nyatike_weather_signals.json",
                 "data/fixtures/migori_pest_alerts.json",
                 "data/fixtures/migori_market_prices.json",
                 ignorenonexistent=True, stdout=StringIO())
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "No current verified KMD bulletin" in html
    # In DEMO_MODE, the synthetic test scenario appears behind a <details>.
    # In production (DEMO_MODE=0), it's hidden — which is correct.
    # We assert the no-notice state is shown; the synthetic block is optional.
    # Must NOT display "Rainfall: None mm" anywhere.
    assert "Rainfall: None mm" not in html
    # Must NOT call a synthetic bulletin a "live station feed".
    assert "live station feed" not in html.lower()


@pytest.mark.django_db
def test_dashboard_shows_no_current_pest_notice_when_only_synthetic(officer_client):
    """When only synthetic pest fixtures are loaded, the dashboard must show
    'No current verified official pest notice available' (NOT 'No pest risk')."""
    call_command("loaddata", "data/fixtures/migori_kachieng_clusters.json",
                 "data/fixtures/migori_kachieng_plots.json",
                 "data/fixtures/migori_crop_calendars.json",
                 "data/fixtures/nyatike_weather_signals.json",
                 "data/fixtures/migori_pest_alerts.json",
                 "data/fixtures/migori_market_prices.json",
                 ignorenonexistent=True, stdout=StringIO())
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "No current verified official pest notice" in html
    # Must NOT claim pests are absent.
    assert "No pest risk" not in html
    # In DEMO_MODE, the synthetic test scenario appears behind a <details>.
    # In production, it's hidden — which is correct.


@pytest.mark.django_db
def test_dashboard_shows_kalro_permission_pending(officer_client):
    """The dashboard must show KALRO permission-pending state for agronomic
    guidance. The v3 dashboard uses user-friendly wording ('currently unavailable',
    'awaiting authorization') rather than the internal technical phrase
    'permission-pending for KALRO maize manual ingestion' (which is kept on
    the dedicated Guidance details page)."""
    call_command("loaddata", "data/fixtures/migori_crop_calendars.json",
                 "data/fixtures/migori_kachieng_clusters.json",
                 "data/fixtures/migori_kachieng_plots.json",
                 ignorenonexistent=True, stdout=StringIO())
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The dashboard must show KALRO-related text indicating permission is pending.
    # The v3 wording is operational, not technical — the detailed licence phrase
    # is on /dashboard/guidance/ (progressive disclosure).
    assert "KALRO" in html, "Dashboard must mention KALRO for the guidance section"
    assert "not yet authorized" in html.lower() or "authorization pending" in html.lower() or "permission pending" in html.lower(), (
        "Dashboard must indicate KALRO guidance is unavailable / awaiting authorization"
    )
    # The 'Local planting dates not specified' notice must still be present
    assert "Local planting dates have not been verified" in html
    # The detailed 'permission-pending for KALRO maize manual ingestion' phrase
    # is no longer on the dashboard — it's on the Guidance details page.
    # Verify the Guidance details page still has it.
    r2 = officer_client.get("/dashboard/guidance/")
    html2 = r2.content.decode("utf-8")
    assert "permission-pending for KALRO maize manual ingestion" in html2, (
        "Guidance details page must contain the technical permission-pending phrase"
    )


@pytest.mark.django_db
def test_dashboard_shows_real_kmd_when_ingested(officer_client):
    """When an officer ingests a real KMD bulletin, the dashboard shows it as current_official."""
    call_command("seed_kachieng_clusters", stdout=StringIO())
    ingest_kmd_bulletin_metadata(
        area_label="Migori County",
        period="7_day_forecast",
        product_type="7 Days Forecast",
        publication_date=dt.date(2026, 10, 5),
        valid_from=dt.date(2026, 10, 5),
        valid_to=dt.date(2026, 10, 12),
        geographic_scope="Migori County",
        coverage_level="county",
        forecast_summary="Showers and thunderstorms over parts of Migori.",
        rainfall_mm=None,
        onset_status="unknown",
        source_url="https://meteo.go.ke/our-products/7-days-forecast",
    )
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "7 Days Forecast" in html
    assert "Kenya Meteorological Department" in html
    # "Rainfall amount: <strong>Not specified in this bulletin</strong>" — the
    # <strong> tag splits the string, so we check for the two parts separately.
    assert "Rainfall:" in html
    assert "Not specified in this bulletin" in html
    # Must NOT show the no-notice state when a real bulletin is loaded.
    assert "No current verified KMD bulletin" not in html


@pytest.mark.django_db
def test_dashboard_shows_regional_label_for_lake_victoria_forecast(officer_client):
    """A Lake Victoria Basin forecast must show the 'Regional forecast covering Migori' label."""
    call_command("seed_kachieng_clusters", stdout=StringIO())
    ingest_kmd_bulletin_metadata(
        area_label="Lake Victoria Basin (covers Migori)",
        period="daily_forecast",
        product_type="Lake Victoria Fishing Forecast",
        publication_date=dt.date(2026, 10, 5),
        geographic_scope="Lake Victoria Basin",
        coverage_level="regional",
        forecast_summary="Wind and wave forecasts for the Lake Victoria Basin.",
        source_url="https://meteo.go.ke/our-products/",
    )
    r = officer_client.get("/dashboard/")
    html = r.content.decode("utf-8")
    assert "Regional forecast covering Migori" in html
    assert "not a Nyatike station observation" in html


# --- SYNTHETIC DATA NEVER RELABELLED --------------------------------------

@pytest.mark.django_db
def test_synthetic_weather_fixtures_marked_synthetic():
    """Synthetic weather fixtures must have synthetic_flag='synthetic' and verification_status='synthetic'."""
    # Load geography + clusters first (FK constraints), then weather.
    call_command("loaddata", "data/fixtures/migori_kachieng_clusters.json",
                 "data/fixtures/migori_kachieng_plots.json",
                 "data/fixtures/nyatike_weather_signals.json",
                 ignorenonexistent=True, stdout=StringIO())
    synthetic_signals = WeatherSignal.objects.filter(synthetic_flag="synthetic")
    assert synthetic_signals.count() >= 3
    for sig in synthetic_signals:
        assert sig.verification_status == "synthetic"
        assert "Synthetic" in sig.source or "synthetic" in sig.source_authority.lower()


@pytest.mark.django_db
def test_synthetic_pest_fixtures_marked_synthetic():
    """Synthetic pest fixtures must be marked synthetic, NOT relabelled as KALRO/KEPHIS/PlantVillage."""
    call_command("loaddata", "data/fixtures/migori_pest_alerts.json",
                 ignorenonexistent=True, stdout=StringIO())
    synthetic_alerts = PestAlert.objects.filter(synthetic_flag="synthetic")
    assert synthetic_alerts.count() >= 3
    for alert in synthetic_alerts:
        assert alert.verification_status == "synthetic"
        # The fixture text must NOT claim to be a real KALRO/KEPHIS/PlantVillage bulletin.
        # Either the source explicitly says "NOT a KALRO" or it avoids the KALRO label entirely.
        assert "NOT a KALRO" in alert.source or "NOT a KEPHIS" in alert.source or "Synthetic" in alert.source
        # Severity must be "not_specified" (we no longer fabricate 'high' severity).
        assert alert.severity == "not_specified"


@pytest.mark.django_db
def test_synthetic_calendar_fixtures_have_no_invented_dates():
    """Synthetic calendar fixtures must NOT invent planting dates from a national manual."""
    # Load geography first (zone FK), then calendar.
    call_command("loaddata", "data/fixtures/migori_kachieng_clusters.json",
                 "data/fixtures/migori_crop_calendars.json",
                 ignorenonexistent=True, stdout=StringIO())
    cc = CropCalendar.objects.get(crop="maize", zone_label="Migori-Low-Mid", season="short_rains")
    # The KALRO maize manual is the source — we must NOT have extracted Sep 15–Oct 20 dates.
    assert cc.planting_window_start is None
    assert cc.planting_window_end is None
    assert cc.activities == []
    # The activities list must NOT contain the old synthetic KALRO rules:
    # "H614", "PH4", "WH505", "3 consecutive rainy days", "5 mm/day", "DAP/NPK".
    activities_text = json.dumps(cc.activities) if cc.activities else ""
    assert "H614" not in activities_text
    assert "PH4" not in activities_text
    assert "WH505" not in activities_text
    assert "5 mm/day" not in activities_text
    assert "DAP" not in activities_text


# --- BORROWED MCP: real client invocation when npx is available -------------

@pytest.mark.django_db
def test_borrowed_mcp_node_falls_back_to_direct_read_when_npx_disabled(officer, monkeypatch):
    """When MAJISHAMBA_BORROWED_MCP_USE_NPX is not set, the node uses the
    direct file fallback and logs it honestly as 'read_direct_fallback'."""
    monkeypatch.setenv("MAJISHAMBA_BORROWED_MCP_USE_NPX", "0")
    monkeypatch.setenv("MAJISHAMBA_SKIP_OLLAMA", "1")
    # Ensure KACH-01 exists.
    call_command("loaddata", "data/fixtures/migori_kachieng_clusters.json",
                 "data/fixtures/migori_kachieng_plots.json",
                 "data/fixtures/migori_crop_calendars.json",
                 "data/fixtures/nyatike_weather_signals.json",
                 "data/fixtures/migori_pest_alerts.json",
                 "data/fixtures/migori_market_prices.json",
                 ignorenonexistent=True, stdout=StringIO())
    call_command("seed_kachieng_clusters", stdout=StringIO())
    from apps.agents.runner import run_advisory_pipeline
    result = run_advisory_pipeline(
        cluster_id="KACH-01", ward="Kachieng", sub_county="Nyatike", county="Migori", actor=officer,
    )
    assert "advisory_id" in result, f"agent failed: {result}"
    from apps.audit.models import AuditEvent
    ev = AuditEvent.objects.filter(tool_name="borrowed_filesystem_mcp").order_by("-created_at").first()
    assert ev is not None
    # The honest status must be one of the documented fallback states.
    assert "read_direct_fallback" in str(ev.outputs_summary) or "mcp_client" in str(ev.outputs_summary), \
        f"unexpected borrowed MCP status: {ev.outputs_summary}"


import json  # used in test_synthetic_calendar_fixtures_have_no_invented_dates
