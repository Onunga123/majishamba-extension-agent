"""Cluster tests — verify the 14-cluster register, idempotency, and preservation of existing data."""
from __future__ import annotations

import pytest
from django.core.management import call_command
from io import StringIO

from apps.advisories.models import Advisory, AdvisoryEvidence
from apps.audit.models import AuditEvent
from apps.clusters.models import FarmerCluster, Household
from apps.mcp_tools.tools import get_cluster_plot_history
from apps.plots.models import Plot


EXPECTED_CLUSTERS = [
    ("KACH-01", "Sori Farmer Cluster", "Sori"),
    ("KACH-02", "Kiranda Farmer Cluster", "Kiranda"),
    ("KACH-03", "Odendo Farmer Cluster", "Odendo"),
    ("KACH-04", "Agolomuok Farmer Cluster", "Agolomuok"),
    ("KACH-05", "Bongu Farmer Cluster", "Bongu"),
    ("KACH-06", "Gunga Farmer Cluster", "Gunga"),
    ("KACH-07", "Kaduro Farmer Cluster", "Kaduro"),
    ("KACH-08", "Kopala Farmer Cluster", "Kopala"),
    ("KACH-09", "Nyamanga Farmer Cluster", "Nyamanga"),
    ("KACH-10", "Obondi Farmer Cluster", "Obondi"),
    ("KACH-11", "Orore Farmer Cluster", "Orore"),
    ("KACH-12", "Raga Farmer Cluster", "Raga"),
    ("KACH-13", "Sidika Farmer Cluster", "Sidika"),
    ("KACH-14", "Wachara Farmer Cluster", "Wachara"),
]


@pytest.mark.django_db
def test_seed_command_creates_14_clusters():
    """Seed command must create exactly 14 clusters with the specified register."""
    call_command("seed_kachieng_clusters", stdout=StringIO())
    assert FarmerCluster.objects.count() == 14
    for cid, name, locality in EXPECTED_CLUSTERS:
        c = FarmerCluster.objects.get(cluster_id=cid)
        assert c.name == name, f"{cid}: name mismatch"
        assert c.locality == locality, f"{cid}: locality mismatch"


@pytest.mark.django_db
def test_seed_command_idempotent():
    """Running seed_kachieng_clusters twice must produce no duplicates."""
    call_command("seed_kachieng_clusters", stdout=StringIO())
    count_after_first = FarmerCluster.objects.count()
    hh_after_first = Household.objects.count()
    plot_after_first = Plot.objects.count()
    call_command("seed_kachieng_clusters", stdout=StringIO())
    assert FarmerCluster.objects.count() == count_after_first, "Re-running created duplicate clusters"
    assert Household.objects.count() == hh_after_first, "Re-running created duplicate households"
    assert Plot.objects.count() == plot_after_first, "Re-running created duplicate plots"


@pytest.mark.django_db
def test_seed_preserves_existing_primary_keys():
    """KACH-01..KACH-03 primary keys must be preserved across seed runs."""
    call_command("seed_kachieng_clusters", stdout=StringIO())
    pks_before = {c.cluster_id: c.pk for c in FarmerCluster.objects.filter(cluster_id__in=["KACH-01", "KACH-02", "KACH-03"])}
    call_command("seed_kachieng_clusters", stdout=StringIO())
    pks_after = {c.cluster_id: c.pk for c in FarmerCluster.objects.filter(cluster_id__in=["KACH-01", "KACH-02", "KACH-03"])}
    assert pks_before == pks_after, "Primary keys changed across idempotent re-runs"


@pytest.mark.django_db
def test_seed_preserves_existing_households_for_original_clusters():
    """KACH-01 originally had 5 households from the fixture — seed must not delete or duplicate them."""
    # Load original fixtures (which set KACH-01 with 5 households)
    call_command("loaddata", "data/fixtures/migori_kachieng_clusters.json",
                 "data/fixtures/migori_kachieng_plots.json", ignorenonexistent=True, stdout=StringIO())
    kach01_hh_before = FarmerCluster.objects.get(cluster_id="KACH-01").households.count()
    assert kach01_hh_before > 0, "Fixture should have loaded KACH-01 households"
    # Run seed
    call_command("seed_kachieng_clusters", stdout=StringIO())
    kach01_hh_after = FarmerCluster.objects.get(cluster_id="KACH-01").households.count()
    assert kach01_hh_after == kach01_hh_before, "Seed changed KACH-01 household count"


@pytest.mark.django_db
def test_new_clusters_have_3_households_1_plot_each():
    """KACH-04..KACH-14 must each have 3 households with 1 plot per household."""
    call_command("seed_kachieng_clusters", stdout=StringIO())
    for cid in [f"KACH-{i:02d}" for i in range(4, 15)]:
        c = FarmerCluster.objects.get(cluster_id=cid)
        assert c.households.count() == 3, f"{cid} should have 3 households, got {c.households.count()}"
        for hh in c.households.all():
            assert hh.plots.count() == 1, f"{cid}/{hh.household_id} should have 1 plot"


@pytest.mark.django_db
def test_kach_14_works_through_mcp_retrieval(officer):
    """KACH-14 must be retrievable through the MCP get_cluster_plot_history tool."""
    call_command("seed_kachieng_clusters", stdout=StringIO())
    res = get_cluster_plot_history(cluster_id="KACH-14", actor_id=officer.id)
    assert res["cluster_id"] == "KACH-14"
    assert res["cluster_name"] == "Wachara Farmer Cluster"
    assert res["ward"] == "Kachieng"
    assert len(res["plots"]) == 3, f"KACH-14 should have 3 plots, got {len(res['plots'])}"


@pytest.mark.django_db
def test_unknown_cluster_id_fails_safely():
    """An unknown cluster_id must return warnings + empty plots, not raise."""
    res = get_cluster_plot_history(cluster_id="KACH-999")
    assert res["cluster_id"] == "KACH-999"
    assert res["plots"] == []
    assert any("not found" in w for w in res.get("warnings", []))


@pytest.mark.django_db
def test_existing_audit_history_remains_unchanged_after_seed(officer):
    """Audit events created BEFORE re-seeding must remain unchanged."""
    # Create an audit event first (simulate prior history)
    from apps.audit.service import log_audit_event
    log_audit_event(actor=officer, action="test:before_seed", metadata={"key": "value"})
    before_count = AuditEvent.objects.filter(action="test:before_seed").count()
    before_meta = list(AuditEvent.objects.filter(action="test:before_seed").values_list("metadata", flat=True))
    # Run seed
    call_command("seed_kachieng_clusters", stdout=StringIO())
    after_count = AuditEvent.objects.filter(action="test:before_seed").count()
    after_meta = list(AuditEvent.objects.filter(action="test:before_seed").values_list("metadata", flat=True))
    assert before_count == after_count, "Seed command wrote/destroyed audit history"
    assert before_meta == after_meta, "Seed command changed audit event metadata"


@pytest.mark.django_db
def test_seed_dry_run_does_not_write():
    """--dry-run must not write anything to the database."""
    count_before = FarmerCluster.objects.count()
    out = StringIO()
    call_command("seed_kachieng_clusters", "--dry-run", stdout=out)
    assert FarmerCluster.objects.count() == count_before, "Dry run wrote to the database"
    output = out.getvalue()
    assert "DRY RUN" in output or "WOULD" in output, "Dry run should announce itself"


@pytest.mark.django_db
def test_seed_report_does_not_write():
    """--report must not write anything to the database."""
    call_command("seed_kachieng_clusters", stdout=StringIO())  # ensure some clusters exist
    count_before = FarmerCluster.objects.count()
    call_command("seed_kachieng_clusters", "--report", stdout=StringIO())
    assert FarmerCluster.objects.count() == count_before


@pytest.mark.django_db
def test_no_cluster_has_invented_coordinates():
    """New clusters KACH-04..KACH-14 must NOT have coordinates (we never invent them).
    Existing KACH-01..KACH-03 keep their fixture synthetic coordinates but
    coordinates_verified=False."""
    call_command("seed_kachieng_clusters", stdout=StringIO())
    for cid in [f"KACH-{i:02d}" for i in range(4, 15)]:
        c = FarmerCluster.objects.get(cluster_id=cid)
        assert c.centroid_lat is None and c.centroid_lon is None, f"{cid} should have no coords"
        assert c.coordinates_verified is False, f"{cid} should not be marked verified"
    for cid in ["KACH-01", "KACH-02", "KACH-03"]:
        c = FarmerCluster.objects.get(cluster_id=cid)
        assert c.coordinates_verified is False, f"{cid} should not be marked verified (coords are synthetic)"
