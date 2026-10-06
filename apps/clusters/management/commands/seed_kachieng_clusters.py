"""Idempotent management command to seed the 14 Kachieng pilot clusters.

Preserves existing KACH-01/02/03 primary keys and their households/plots/advisories.
Updates display names and locality metadata to the locally-confirmed register.
Creates KACH-04..KACH-14 with three synthetic households and one synthetic maize plot each.

Usage:
    python manage.py seed_kachieng_clusters            # apply
    python manage.py seed_kachieng_clusters --dry-run  # preview only
    python manage.py seed_kachieng_clusters --report    # print current totals only

Idempotent: running twice produces no duplicates and does not overwrite
existing household records or historical evidence.

Geographic verification:
    verification_status: locally_confirmed
    verification_method: project_owner_local_knowledge
    verified_by: Onunga Christopher
    verification_date: 2026-10-06

Local confirmation of a name does NOT establish coordinates or make the
farmer groups real. All farmer/household/plot/yield data is explicitly
synthetic. We do not invent coordinates for new clusters.
"""
from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.clusters.models import FarmerCluster, Household
from apps.geography.models import ExtensionOffice, Ward
from apps.plots.models import CropSeasonRecord, Plot

# The exact register requested by the project owner.
# locality = the geographic type (NOT an admin village-unit/sub-location).
CLUSTERS_REGISTER: list[tuple[str, str, str]] = [
    # (cluster_id, name, locality)
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

# Existing KACH-01/02/03 had synthetic centroid coords in the fixture.
# Mark them as coordinates_verified=False so the UI labels them synthetic
# (which they are — no real coordinates were ever collected).
# New clusters KACH-04..KACH-14 get NO coordinates (NULL) and
# coordinates_verified=False — we never invent coordinates.
EXISTING_COORDS: dict[str, tuple[float, float]] = {
    "KACH-01": (-0.952, 34.432),
    "KACH-02": (-0.970, 34.445),
    "KACH-03": (-0.982, 34.458),
}

VERIFICATION_RECORD = {
    "verification_status": "locally_confirmed",
    "verification_method": "project_owner_local_knowledge",
    "verified_by": "Onunga Christopher",
    "verification_date": "2026-10-06",
    "geographic_type": "locality",
}


def _ensure_ward_and_office() -> tuple[Ward, ExtensionOffice]:
    """Get or create the Kachieng ward and Nyatike office.

    These were created by the original fixture, but we re-create them
    defensively in case the command runs against an empty DB.
    """
    from apps.geography.models import County, SubCounty
    county, _ = County.objects.get_or_create(name="Migori", defaults={"code": "MG-20"})
    sub, _ = SubCounty.objects.get_or_create(county=county, name="Nyatike", defaults={"code": "NYA-01"})
    ward, _ = Ward.objects.get_or_create(
        sub_county=sub, name="Kachieng",
        defaults={"code": "KACH", "centroid_lat": -0.965, "centroid_lon": 34.445},
    )
    office, _ = ExtensionOffice.objects.get_or_create(
        name="Nyatike Sub-County Agricultural Office",
        defaults={"sub_county": sub, "ward": ward, "contact": "+254 700 000 000 (synthetic)"},
    )
    return ward, office


def _ensure_households_and_plots(cluster: FarmerCluster) -> tuple[int, int]:
    """For each NEW cluster (KACH-04..KACH-14): create exactly 3 synthetic
    households, each with one synthetic maize plot. For EXISTING clusters
    (KACH-01..KACH-03): leave existing households/plots untouched.

    Returns (households_created, plots_created) for reporting.
    """
    if cluster.cluster_id in {"KACH-01", "KACH-02", "KACH-03"}:
        return 0, 0
    hh_created = 0
    plot_created = 0
    for i in range(1, 4):
        hh_id = f"{cluster.cluster_id}-HH-{i:03d}"
        hh, created = Household.objects.get_or_create(
            household_id=hh_id,
            defaults={
                "cluster": cluster,
                "head_of_household": f"Synthetic — Head {i}",
                "notes": "Synthetic household seeded by seed_kachieng_clusters command. Not a real person.",
            },
        )
        if created:
            hh_created += 1
        plot_id = f"{hh_id}-P1"
        plot, p_created = Plot.objects.get_or_create(
            plot_id=plot_id,
            defaults={
                "household": hh,
                "area_ha": 0.5,
                "soil_type": Plot.SoilType.LOAM,
                "irrigation": False,
                "notes": "Synthetic plot seeded by seed_kachieng_clusters command.",
            },
        )
        if p_created:
            plot_created += 1
            # One synthetic 2023 short-rains maize season record per plot
            CropSeasonRecord.objects.get_or_create(
                plot=plot, season="2023 short_rains", crop="maize",
                defaults={
                    "outcome": CropSeasonRecord.Outcome.SUCCESS,
                    "yield_band": CropSeasonRecord.YieldBand.MEDIUM,
                    "notes": "Synthetic season record seeded by seed_kachieng_clusters command.",
                },
            )
    return hh_created, plot_created


class Command(BaseCommand):
    help = "Idempotently seed the 14 Kachieng pilot clusters (preserves KACH-01..KACH-03 data)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Preview changes without writing to the database.",
        )
        parser.add_argument(
            "--report", action="store_true",
            help="Print current cluster/household/plot totals and exit (no changes).",
        )

    def handle(self, *args, **options):
        if options.get("report"):
            self._report_totals()
            return

        dry_run = bool(options.get("dry_run"))
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no database changes will be made."))

        ward, office = _ensure_ward_and_office()

        actions: list[str] = []
        clusters_created = 0
        clusters_renamed = 0
        households_created = 0
        plots_created = 0

        with transaction.atomic():
            for cluster_id, name, locality in CLUSTERS_REGISTER:
                coords = EXISTING_COORDS.get(cluster_id)
                notes = (
                    f"Locality name confirmed by project owner (verification_status={VERIFICATION_RECORD['verification_status']}, "
                    f"verification_method={VERIFICATION_RECORD['verification_method']}, "
                    f"verified_by={VERIFICATION_RECORD['verified_by']}, "
                    f"verification_date={VERIFICATION_RECORD['verification_date']}). "
                    f"Geographic type: {VERIFICATION_RECORD['geographic_type']}. "
                    f"Coordinates are synthetic placeholders (coordinates_verified=False). "
                    f"All farmer/household/plot/yield data is synthetic."
                )
                if cluster_id in {"KACH-01", "KACH-02", "KACH-03"}:
                    # Existing cluster — update name + locality, preserve PK and households.
                    try:
                        cluster = FarmerCluster.objects.get(cluster_id=cluster_id)
                    except FarmerCluster.DoesNotExist:
                        if dry_run:
                            actions.append(f"WOULD create {cluster_id} (currently missing)")
                            clusters_created += 1
                            continue
                        cluster = FarmerCluster(cluster_id=cluster_id, ward=ward, office=office)
                        clusters_created += 1
                        actions.append(f"create {cluster_id} (was missing)")
                    if cluster.name != name or cluster.locality != locality:
                        actions.append(
                            f"WOULD rename {cluster_id}: '{cluster.name}' → '{name}' (locality='{locality}')"
                        )
                        clusters_renamed += 1
                    if not dry_run:
                        cluster.name = name
                        cluster.locality = locality
                        cluster.ward = ward
                        cluster.office = office
                        if coords:
                            cluster.centroid_lat, cluster.centroid_lon = coords
                        cluster.coordinates_verified = False
                        cluster.notes = notes
                        cluster.save()
                else:
                    # New cluster KACH-04..KACH-14
                    existing = FarmerCluster.objects.filter(cluster_id=cluster_id).first()
                    if existing is None:
                        if dry_run:
                            actions.append(f"WOULD create {cluster_id} — {name} (locality={locality})")
                            clusters_created += 1
                            continue
                        cluster = FarmerCluster.objects.create(
                            cluster_id=cluster_id,
                            name=name,
                            ward=ward,
                            office=office,
                            representative=f"Synthetic rep — {locality}",
                            contact="+254 700 000 000 (synthetic)",
                            locality=locality,
                            centroid_lat=None,
                            centroid_lon=None,
                            coordinates_verified=False,
                            notes=notes,
                        )
                        clusters_created += 1
                        actions.append(f"create {cluster_id} — {name} (locality={locality})")
                    else:
                        cluster = existing
                        changed = False
                        if cluster.name != name:
                            actions.append(f"WOULD rename {cluster_id}: '{cluster.name}' → '{name}'")
                            if not dry_run:
                                cluster.name = name
                            changed = True
                        if cluster.locality != locality:
                            actions.append(f"WOULD set {cluster_id} locality='{locality}'")
                            if not dry_run:
                                cluster.locality = locality
                            changed = True
                        if cluster.ward_id != ward.id:
                            if not dry_run:
                                cluster.ward = ward
                            changed = True
                        if cluster.office_id != office.id:
                            if not dry_run:
                                cluster.office = office
                            changed = True
                        if changed:
                            clusters_renamed += 1
                            if not dry_run:
                                cluster.notes = notes
                                cluster.save()

                if not dry_run:
                    hh, pl = _ensure_households_and_plots(cluster)
                    households_created += hh
                    plots_created += pl

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run complete. No changes written."))
            self.stdout.write("Planned actions:")
            for a in actions:
                self.stdout.write(f"  - {a}")
        else:
            self.stdout.write(self.style.SUCCESS(f"Seeded {len(CLUSTERS_REGISTER)} clusters."))
            self.stdout.write(f"  clusters_created:    {clusters_created}")
            self.stdout.write(f"  clusters_renamed:    {clusters_renamed}")
            self.stdout.write(f"  households_created:  {households_created}")
            self.stdout.write(f"  plots_created:       {plots_created}")
        self._report_totals()

    def _report_totals(self) -> None:
        """Report actual cluster/household/plot totals in the database now.
        Do NOT assume a total — count what's actually there.
        """
        cluster_count = FarmerCluster.objects.count()
        household_count = Household.objects.count()
        plot_count = Plot.objects.count()
        season_count = CropSeasonRecord.objects.count()
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_200_LEVEL_INFO if False else "Current totals (actual counts):")
        self.stdout.write(f"  clusters:          {cluster_count}")
        self.stdout.write(f"  households:         {household_count}")
        self.stdout.write(f"  plots:              {plot_count}")
        self.stdout.write(f"  season_records:     {season_count}")
        self.stdout.write(f"  clusters with locality set: {FarmerCluster.objects.exclude(locality='').count()}")
        self.stdout.write(f"  clusters with verified coords: {FarmerCluster.objects.filter(coordinates_verified=True).count()}")
        self.stdout.write("")
        self.stdout.write("Verification record:")
        for k, v in VERIFICATION_RECORD.items():
            self.stdout.write(f"  {k}: {v}")
