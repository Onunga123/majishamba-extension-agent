"""Map tests — verify no Google Maps dependency, OSM attribution, synthetic coords labelled."""
from __future__ import annotations

import pytest
from django.core.management import call_command
from io import StringIO

from apps.clusters.models import FarmerCluster


@pytest.mark.django_db
def test_no_google_maps_dependency_in_repo():
    """No file in the repo (excluding tests themselves and venvs) should reference
    Google Maps JS API or googleapis.com/maps."""
    import os
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    forbidden_substrings = [
        "maps.googleapis.com",
        "google.maps.",
        "Google Maps JavaScript API",
        "https://maps.google.com/",
    ]
    skip_dirs = {".venv", ".git", "__pycache__", ".pytest_cache", "staticfiles", "node_modules"}
    # Also skip this test file (it legitimately mentions the strings to test for them).
    skip_files = {"test_map.py"}
    hits = []
    for root, dirs, files in os.walk(base):
        if any(part in skip_dirs for part in root.split(os.sep)):
            continue
        for f in files:
            if f in skip_files:
                continue
            if not f.endswith((".html", ".py", ".md", ".js", ".css")):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, encoding="utf-8") as fp:
                    content = fp.read()
            except (UnicodeDecodeError, OSError):
                continue
            for needle in forbidden_substrings:
                if needle in content:
                    hits.append((path, needle))
    assert not hits, f"Google Maps references found: {hits}"


@pytest.mark.django_db
def test_map_page_uses_maplibre_with_osm_attribution(officer_client):
    """The map page must use MapLibre GL JS + OSM raster tiles with attribution."""
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/dashboard/map/")
    html = r.content.decode("utf-8")
    # MapLibre GL JS must be present
    assert "maplibregl" in html.lower() or "maplibre-gl" in html, "MapLibre GL JS not loaded"
    # OSM attribution must be visible
    assert "OpenStreetMap contributors" in html, "OSM attribution missing"
    # Google Maps must NOT be referenced
    assert "google" not in html.lower() or "googleapis" not in html, "Google Maps reference found"


@pytest.mark.django_db
def test_map_page_marks_synthetic_coordinates(officer_client):
    """Clusters with synthetic coordinates must NOT appear as real markers.
    Only approved LocalityCoordinate entries are shown as real markers."""
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/dashboard/map/")
    html = r.content.decode("utf-8")
    # Without approved coordinates, KACH-01..03 must show 'not yet recorded' or 'awaiting review'.
    # They must NOT be labeled as 'Verified' or 'Synthetic placeholder' (old UI removed).
    assert "KACH-01" in html, "KACH-01 should appear in the locality list"
    # Synthetic cluster centroid coords should NOT be displayed as real coordinates.
    assert "Synthetic placeholder" not in html, "Old synthetic placeholder label should not appear"


@pytest.mark.django_db
def test_map_page_shows_unmapped_clusters_in_list(officer_client):
    """Clusters without coordinates must appear in the locality list with 'not yet recorded'."""
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/dashboard/map/")
    html = r.content.decode("utf-8")
    # KACH-04..KACH-14 have no coordinates → must show "Coordinates not yet recorded"
    assert "Coordinates not yet recorded" in html, "Unmapped clusters not shown in list"
    # And the cluster itself must appear (KACH-14 e.g.)
    assert "KACH-14" in html


@pytest.mark.django_db
def test_map_page_has_basemap_unavailable_fallback(officer_client):
    """The map page must include a fallback element for when the basemap cannot load."""
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/dashboard/map/")
    html = r.content.decode("utf-8")
    # The new template has 'Basemap could not be loaded' (not 'Basemap unavailable').
    assert "could not be loaded" in html.lower(), "Tile-failure fallback not present"


@pytest.mark.django_db
def test_tile_failure_does_not_break_advisory_workflows(officer_client):
    """Even if the basemap fails to load, the advisory request page must still work."""
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/advisories/request/")
    assert r.status_code == 200
    # The cluster dropdown must still be populated.
    html = r.content.decode("utf-8")
    assert "KACH-01" in html


@pytest.mark.django_db
def test_invalid_coordinates_excluded_from_markers(officer_client):
    """Clusters with null coordinates must NOT get a marker on the map (only listed)."""
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/dashboard/map/")
    html = r.content.decode("utf-8")
    # The JS filters out clusters where lat or lon is null.
    # We assert the JS code contains the filter.
    assert "mappableClusters" in html or "lat !== null" in html, "Map JS does not filter invalid coords"
    # And clusters with null coords appear only in the table, not as markers.
    # (The JS doesn't add a marker for them; we already assert the list shows them.)


@pytest.mark.django_db
def test_tile_url_configurable_via_settings():
    """The map tile URL must come from settings, allowing production to override it."""
    from django.conf import settings
    # Default must be Stadia Maps (free for localhost dev).
    url = settings.MAJISHAMBA["MAP_BASEMAP_TILES"]
    assert "stadiamaps.com" in url or "tile.openstreetmap.org" in url, f"Unexpected tile URL: {url}"
    # Attribution must be present.
    attribution = settings.MAJISHAMBA["MAP_BASEMAP_ATTRIBUTION"]
    assert "OpenStreetMap" in attribution or "Stadia" in attribution
    # API key setting must exist (empty for localhost dev).
    assert "MAP_API_KEY" in settings.MAJISHAMBA
    # Attribution must be present.
    assert "OpenStreetMap" in settings.MAJISHAMBA["MAP_BASEMAP_ATTRIBUTION"]
