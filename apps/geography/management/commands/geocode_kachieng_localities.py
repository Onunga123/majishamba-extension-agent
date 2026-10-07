"""Geocode the 14 Kachieng localities using the public Nominatim API.

Usage policy compliance:
- Single-threaded, one request per second (Nominatim usage policy).
- Identifying User-Agent.
- One-time lookup, results cached in the database (LocalityCoordinate model).
- No autocomplete, no per-page-load geocoding.

Usage:
    python manage.py geocode_kachieng_localities          # run lookup
    python manage.py geocode_kachieng_localities --dry-run # preview candidates without writing
    python manage.py geocode_kachieng_localities --review  # show candidates awaiting review
    python manage.py geocode_kachieng_localities --approve KACH-01  # approve a candidate

Candidates are NOT displayed as confirmed markers until an officer approves them.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Any

import httpx
from django.core.management.base import BaseCommand

logger = logging.getLogger("majishamba.geocode")


LOCALITY_SEARCHES: list[dict[str, str]] = [
    {"cluster_id": "KACH-01", "locality": "Sori", "search": "Sori, Nyatike, Migori, Kenya"},
    {"cluster_id": "KACH-02", "locality": "Kiranda", "search": "Kiranda, Nyatike, Migori, Kenya"},
    {"cluster_id": "KACH-03", "locality": "Odendo", "search": "Odendo, Nyatike, Migori, Kenya"},
    {"cluster_id": "KACH-04", "locality": "Agolomuok", "search": "Agolomuok, Nyatike, Migori, Kenya"},
    {"cluster_id": "KACH-05", "locality": "Bongu", "search": "Bongu, Nyatike, Migori, Kenya"},
    {"cluster_id": "KACH-06", "locality": "Gunga", "search": "Gunga, Nyatike, Migori, Kenya"},
    {"cluster_id": "KACH-07", "locality": "Kaduro", "search": "Kaduro, Nyatike, Migori, Kenya"},
    {"cluster_id": "KACH-08", "locality": "Kopala", "search": "Kopala, Nyatike, Migori, Kenya"},
    {"cluster_id": "KACH-09", "locality": "Nyamanga", "search": "Nyamanga, Nyatike, Migori, Kenya"},
    {"cluster_id": "KACH-10", "locality": "Obondi", "search": "Obondi, Nyatike, Migori, Kenya"},
    {"cluster_id": "KACH-11", "locality": "Orore", "search": "Orore, Nyatike, Migori, Kenya"},
    {"cluster_id": "KACH-12", "locality": "Raga", "search": "Raga, Nyatike, Migori, Kenya"},
    {"cluster_id": "KACH-13", "locality": "Sidika", "search": "Sidika, Nyatike, Migori, Kenya"},
    {"cluster_id": "KACH-14", "locality": "Wachara", "search": "Wachara, Nyatike, Migori, Kenya"},
]


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "KachiengAIAgent/0.1 (kachieng-ai-agent; project owner Onunga Christopher)"


def _nominatim_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en"}
    params = {"q": query, "format": "json", "limit": str(limit), "addressdetails": "1", "extratags": "1"}
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(NOMINATIM_URL, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Nominatim search failed for %r: %s", query, exc)
        return []


def _classify_candidate(cand: dict[str, Any]) -> dict[str, Any]:
    addr = cand.get("address", {}) or {}
    admin_context = ", ".join(
        v for v in [
            addr.get("village") or addr.get("town") or addr.get("hamlet"),
            addr.get("county"),
            addr.get("state"),
            addr.get("country"),
        ] if v
    )
    return {
        "feature_name": cand.get("display_name", ""),
        "feature_type": cand.get("type") or cand.get("class") or "",
        "lat": float(cand.get("lat", 0)),
        "lon": float(cand.get("lon", 0)),
        "osm_id": str(cand.get("osm_id", "")),
        "osm_type": cand.get("osm_type", ""),
        "source_url": f"https://www.openstreetmap.org/{cand.get('osm_type','')}/{cand.get('osm_id','')}" if cand.get("osm_id") else "",
        "admin_context": admin_context,
        "importance": cand.get("importance", 0),
    }


class Command(BaseCommand):
    help = "Geocode the 14 Kachieng localities via Nominatim (rate-limited, cached, reviewable)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview candidates without writing.")
        parser.add_argument("--review", action="store_true", help="Show all candidates awaiting review.")
        parser.add_argument("--approve", type=str, help="Approve the best candidate for a cluster_id.")
        parser.add_argument("--reject", type=str, help="Reject all candidates for a cluster_id.")

    def handle(self, *args, **options):
        if options.get("review"):
            return self._show_review()
        if options.get("approve"):
            return self._approve(options["approve"])
        if options.get("reject"):
            return self._reject(options["reject"])
        self._geocode(dry_run=bool(options.get("dry_run")))

    def _geocode(self, dry_run: bool) -> None:
        from apps.geography.models import LocalityCoordinate
        self.stdout.write("Geocoding 14 Kachieng localities via Nominatim...")
        self.stdout.write(f"User-Agent: {USER_AGENT}")
        self.stdout.write(f"Rate limit: 1 request per second")
        self.stdout.write("")

        for i, search in enumerate(LOCALITY_SEARCHES):
            self.stdout.write(f"[{i+1}/14] {search['cluster_id']} — {search['locality']}...")
            candidates_raw = _nominatim_search(search["search"], limit=5)
            if not candidates_raw:
                self.stdout.write(self.style.WARNING(f"  No results."))
            else:
                candidates = [_classify_candidate(c) for c in candidates_raw]
                for j, c in enumerate(candidates):
                    self.stdout.write(f"  [{j+1}] {c['feature_name'][:80]}")
                    self.stdout.write(f"      type={c['feature_type']} lat={c['lat']:.4f} lon={c['lon']:.4f} context={c['admin_context']}")
                    self.stdout.write(f"      source={c['source_url']}")
                if not dry_run:
                    self._store_candidates(search["cluster_id"], search["locality"], candidates)
            if i < len(LOCALITY_SEARCHES) - 1:
                time.sleep(1.0)
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Done. Run --review to see candidates, --approve KACH-01 to approve."))

    def _store_candidates(self, cluster_id: str, locality: str, candidates: list[dict]) -> None:
        from apps.geography.models import LocalityCoordinate
        from apps.clusters.models import FarmerCluster
        if not candidates:
            return
        best = candidates[0]
        try:
            cluster = FarmerCluster.objects.get(cluster_id=cluster_id)
        except FarmerCluster.DoesNotExist:
            return
        LocalityCoordinate.objects.update_or_create(
            cluster=cluster,
            defaults={
                "locality_name": locality,
                "latitude": best["lat"],
                "longitude": best["lon"],
                "coordinate_source": "OpenStreetMap Nominatim",
                "source_feature_id": best["osm_id"],
                "source_url": best["source_url"],
                "coordinate_type": "settlement_reference",
                "verification_status": "candidate",
                "notes": f"Feature: {best['feature_name']}. Type: {best['feature_type']}. Context: {best['admin_context']}.",
            },
        )

    def _show_review(self) -> None:
        from apps.geography.models import LocalityCoordinate
        coords = LocalityCoordinate.objects.select_related("cluster").all()
        if not coords:
            self.stdout.write("No coordinates. Run without --review first.")
            return
        for c in coords:
            self.stdout.write(f"{c.cluster.cluster_id} — {c.locality_name} — lat={c.latitude:.4f} lon={c.longitude:.4f} — status={c.verification_status}")

    def _approve(self, cluster_id: str) -> None:
        from apps.geography.models import LocalityCoordinate
        try:
            coord = LocalityCoordinate.objects.get(cluster__cluster_id=cluster_id)
        except LocalityCoordinate.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"No coordinate for {cluster_id}."))
            return
        coord.verification_status = "approved"
        coord.coordinate_type = "owner_confirmed_reference"
        coord.verified_by = "Officer (via management command)"
        coord.verified_at = dt.datetime.now()
        coord.save()
        self.stdout.write(self.style.SUCCESS(f"Approved {cluster_id}."))

    def _reject(self, cluster_id: str) -> None:
        from apps.geography.models import LocalityCoordinate
        try:
            coord = LocalityCoordinate.objects.get(cluster__cluster_id=cluster_id)
        except LocalityCoordinate.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"No coordinate for {cluster_id}."))
            return
        coord.verification_status = "rejected"
        coord.save()
        self.stdout.write(self.style.WARNING(f"Rejected {cluster_id}."))
