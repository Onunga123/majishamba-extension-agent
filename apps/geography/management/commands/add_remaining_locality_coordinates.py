"""Add coordinates for the 10 Kachieng localities that Nominatim couldn't find.

These are small villages in rural Kachieng' Ward, Nyatike Sub-County, Migori County, Kenya.
The coordinates are approximate — based on the geographic context of Kachieng' Ward
(centered near Sori/Kiranda at approximately -0.83, 34.14) and the relative positions
of the localities as described by the project owner.

All coordinates are stored as 'candidate' verification_status (NOT 'approved') and
coordinate_type 'settlement_reference'. They must be reviewed and approved by an
authorized officer before being displayed as verified.

Usage:
    python manage.py add_remaining_locality_coordinates
    python manage.py add_remaining_locality_coordinates --dry-run
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from apps.geography.models import LocalityCoordinate
from apps.clusters.models import FarmerCluster


# Approximate coordinates for the 10 localities not found by Nominatim.
# These are based on the geographic context of Kachieng' Ward and the
# project owner's knowledge of the area. They are candidates, NOT verified.
# Source: Project owner local knowledge (Christopher Onunga, from Kachieng')
REMAINING_COORDINATES = {
    "KACH-03": {"locality": "Odendo", "lat": -0.8350, "lon": 34.1450},
    "KACH-05": {"locality": "Bongu", "lat": -0.8200, "lon": 34.1300},
    "KACH-07": {"locality": "Kaduro", "lat": -0.8150, "lon": 34.1100},
    "KACH-08": {"locality": "Kopala", "lat": -0.8100, "lon": 34.1200},
    "KACH-09": {"locality": "Nyamanga", "lat": -0.8250, "lon": 34.1100},
    "KACH-10": {"locality": "Obondi", "lat": -0.8180, "lon": 34.1350},
    "KACH-11": {"locality": "Orore", "lat": -0.8220, "lon": 34.1250},
    "KACH-12": {"locality": "Raga", "lat": -0.8300, "lon": 34.1000},
    "KACH-13": {"locality": "Sidika", "lat": -0.8400, "lon": 34.1100},
    "KACH-14": {"locality": "Wachara", "lat": -0.8280, "lon": 34.1500},
}


class Command(BaseCommand):
    help = "Add approximate coordinates for localities not found by Nominatim. All stored as candidates."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview without writing")

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        added = 0
        skipped = 0

        for cluster_id, coords in REMAINING_COORDINATES.items():
            try:
                cluster = FarmerCluster.objects.get(cluster_id=cluster_id)
            except FarmerCluster.DoesNotExist:
                self.stderr.write(f"  SKIP {cluster_id} — cluster not found")
                skipped += 1
                continue

            # Check if a coordinate already exists
            if hasattr(cluster, "locality_coordinate"):
                self.stdout.write(f"  SKIP {cluster_id} — coordinate already exists (status: {cluster.locality_coordinate.verification_status})")
                skipped += 1
                continue

            if not dry_run:
                LocalityCoordinate.objects.create(
                    cluster=cluster,
                    locality_name=coords["locality"],
                    latitude=coords["lat"],
                    longitude=coords["lon"],
                    coordinate_source="Project owner local knowledge (approximate)",
                    coordinate_type=LocalityCoordinate.CoordinateType.SETTLEMENT_REFERENCE,
                    verification_status=LocalityCoordinate.VerificationStatus.CANDIDATE,
                    notes="Approximate coordinate based on project owner knowledge. Not yet verified via OSM or GPS.",
                )
            self.stdout.write(f"  {'DRY RUN: ' if dry_run else ''}Added {cluster_id} {coords['locality']} lat={coords['lat']} lon={coords['lon']} (candidate)")
            added += 1

        self.stdout.write(f"\nDone. Added: {added}, Skipped: {skipped}")
        if dry_run:
            self.stdout.write("(dry run — no records written)")
