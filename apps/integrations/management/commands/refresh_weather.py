"""Management command to refresh weather from Open-Meteo API.

Usage:
    python manage.py refresh_weather            # fetch for all approved locality coords
    python manage.py refresh_weather --dry-run   # preview without writing
    python manage.py refresh_weather --cluster KACH-01  # fetch for one cluster only

Scheduled job (crontab):
    0 */6 * * * cd /path/to/majishamba && .venv/bin/python manage.py refresh_weather
"""
from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger("majishamba.refresh_weather")


class Command(BaseCommand):
    help = "Refresh weather data from Open-Meteo API for all approved locality coordinates."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB.")
        parser.add_argument("--cluster", type=str, help="Fetch for a specific cluster_id only.")

    def handle(self, *args, **options):
        from apps.geography.models import LocalityCoordinate
        from apps.integrations.open_meteo import ingest_open_meteo_forecast

        dry_run = bool(options.get("dry_run"))
        cluster_filter = options.get("cluster")

        qs = LocalityCoordinate.objects.filter(
            verification_status="approved",
            coordinate_type__in=["owner_confirmed_reference", "settlement_reference"],
        ).select_related("cluster")

        if cluster_filter:
            qs = qs.filter(cluster__cluster_id=cluster_filter)

        coords = list(qs)
        if not coords:
            self.stdout.write(self.style.WARNING("No approved locality coordinates found."))
            self.stdout.write("Run `python manage.py geocode_kachieng_localities` and approve candidates first.")
            return

        self.stdout.write(f"Refreshing weather from Open-Meteo for {len(coords)} location(s)...")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no API calls will be made."))
            for c in coords:
                self.stdout.write(f"  Would fetch for {c.cluster.cluster_id} ({c.locality_name}) at {c.latitude:.4f}, {c.longitude:.4f}")
            return

        success_count = 0
        fail_count = 0
        for c in coords:
            self.stdout.write(f"  Fetching {c.cluster.cluster_id} — {c.locality_name} ({c.latitude:.4f}, {c.longitude:.4f})...")
            result = ingest_open_meteo_forecast(
                latitude=c.latitude,
                longitude=c.longitude,
                locality_name=c.locality_name,
                cluster_id=c.cluster.cluster_id,
            )
            if result["success"]:
                success_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f"    OK: {result['forecast_days']} days, {result['first_date']} to {result['last_date']}, "
                    f"elevation={result.get('elevation', '?')}m"
                ))
            else:
                fail_count += 1
                self.stdout.write(self.style.ERROR(f"    FAILED: {result.get('errors', ['unknown'])}"))

        self.stdout.write("")
        self.stdout.write(f"Done: {success_count} succeeded, {fail_count} failed.")
