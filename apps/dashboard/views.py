"""Officer dashboard views — map, cluster list, advisory review."""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import render
from django.views import View

from apps.advisories.models import Advisory
from apps.audit.models import AuditEvent
from apps.clusters.models import FarmerCluster
from apps.integrations.kalro import permission_status as kalro_permission_status
from apps.integrations.kmd import no_current_kmd_notice
from apps.integrations.pests import no_current_pest_notice
from apps.pests.models import PestAlert
from apps.tasks.models import FollowUpTask
from apps.weather.models import WeatherSignal


def _latest_real_weather():
    """Return the most recent NON-synthetic WeatherSignal, or None."""
    return (
        WeatherSignal.objects
        .exclude(synthetic_flag="synthetic")
        .order_by("-publication_date", "-source_date", "-retrieved_at")
        .first()
    )


def _latest_synthetic_weather():
    """Return the most recent synthetic WeatherSignal (clearly labelled), or None."""
    return (
        WeatherSignal.objects
        .filter(synthetic_flag="synthetic")
        .order_by("-publication_date", "-source_date", "-retrieved_at")
        .first()
    )


def _latest_real_pest_notice():
    """Return the most recent NON-synthetic, currently-valid PestAlert, or None."""
    return (
        PestAlert.objects
        .exclude(synthetic_flag="synthetic")
        .filter(verification_status__in=["current_official", "officer_field_report"])
        .order_by("-publication_date", "-source_date", "-retrieved_at")
        .first()
    )


def _latest_synthetic_pest_notice():
    """Return the most recent synthetic PestAlert (clearly labelled), or None."""
    return (
        PestAlert.objects
        .filter(synthetic_flag="synthetic")
        .order_by("-publication_date", "-source_date", "-retrieved_at")
        .first()
    )


class DashboardHomeView(LoginRequiredMixin, View):
    def get(self, request):
        clusters = list(FarmerCluster.objects.select_related("ward__sub_county__county").all())
        cluster_stats = []
        for c in clusters:
            cluster_stats.append({
                "cluster": c,
                "household_count": c.households.count(),
                "plot_count": sum(h.plots.count() for h in c.households.all()),
                "advisory_count": c.advisories.count(),
                "draft_count": c.advisories.filter(status=Advisory.Status.DRAFT).count(),
                "approved_count": c.advisories.filter(status=Advisory.Status.APPROVED).count(),
            })

        recent_advisories = Advisory.objects.select_related("cluster").order_by("-created_at")[:10]
        recent_events = AuditEvent.objects.select_related("actor").order_by("-created_at")[:25]
        pending_tasks = FollowUpTask.objects.exclude(status=FollowUpTask.Status.COMPLETED).order_by("deadline")[:10]
        # Badges for the nav and dashboard
        draft_advisory_count = Advisory.objects.filter(status=Advisory.Status.DRAFT).count()
        pending_task_count = FollowUpTask.objects.exclude(status=FollowUpTask.Status.COMPLETED).count()

        # --- Honest weather state ---
        real_weather = _latest_real_weather()
        synthetic_weather = _latest_synthetic_weather()
        if real_weather:
            weather_panel = {
                "kind": "real",
                "signal": real_weather,
                "rainfall_display": real_weather.rainfall_display,
                "is_regional": real_weather.is_regional_context,
            }
        else:
            weather_panel = {
                "kind": "no_current_notice",
                "no_notice": no_current_kmd_notice(),
                "synthetic_for_demo": synthetic_weather,
            }

        # --- Honest pest state ---
        real_pest = _latest_real_pest_notice()
        synthetic_pest = _latest_synthetic_pest_notice()
        if real_pest:
            pest_panel = {
                "kind": "real",
                "alert": real_pest,
                "severity_display": real_pest.severity_display_safe,
            }
        else:
            pest_panel = {
                "kind": "no_current_notice",
                "no_notice": no_current_pest_notice(),
                "synthetic_for_demo": synthetic_pest,
            }

        # --- KALRO permission state ---
        kalro_state = kalro_permission_status()

        return render(
            request,
            "dashboard/home.html",
            {
                "clusters": clusters,
                "cluster_stats": cluster_stats,
                "cluster_count": len(clusters),
                "recent_advisories": recent_advisories,
                "recent_events": recent_events,
                "pending_tasks": pending_tasks,
                "draft_advisory_count": draft_advisory_count,
                "pending_task_count": pending_task_count,
                "weather_panel": weather_panel,
                "pest_panel": pest_panel,
                "kalro_state": kalro_state,
                "office_name": "Nyatike Sub-County Agricultural Office (intended user)",
                "ward": "Kachieng",
                "sub_county": "Nyatike",
                "county": "Migori",
            },
        )


class ClusterMapView(LoginRequiredMixin, View):
    def get(self, request):
        clusters = list(FarmerCluster.objects.select_related("ward__sub_county__county", "locality_coordinate").all())
        # Build GeoJSON-like features for the map JS.
        # Only approved LocalityCoordinate entries get real coordinates.
        mapped_count = 0
        unmapped_count = 0
        localities_for_template: list[dict] = []
        for c in clusters:
            has_coord = (
                hasattr(c, "locality_coordinate")
                and c.locality_coordinate.verification_status == "approved"
                and c.locality_coordinate.coordinate_type != "synthetic"
            )
            if has_coord:
                lc = c.locality_coordinate
                localities_for_template.append({
                    "cluster_id": c.cluster_id,
                    "name": c.name,
                    "locality": c.locality or lc.locality_name,
                    "lat": lc.latitude,
                    "lon": lc.longitude,  # NOTE: this is longitude, used as [lng, lat] in GeoJSON
                    "coordinate_type": lc.coordinate_type,
                    "coordinate_source": lc.coordinate_source,
                    "source_url": lc.source_url,
                    "households": c.households.count(),
                    "verified_by": lc.verified_by,
                    "has_real_coords": True,
                })
                mapped_count += 1
            else:
                localities_for_template.append({
                    "cluster_id": c.cluster_id,
                    "name": c.name,
                    "locality": c.locality or "",
                    "lat": None,
                    "lon": None,
                    "households": c.households.count(),
                    "has_real_coords": False,
                    "notes": "Coordinates not yet recorded" if not hasattr(c, "locality_coordinate") else f"Awaiting review (status: {c.locality_coordinate.verification_status})",
                })
                unmapped_count += 1
        cfg = settings.MAJISHAMBA
        return render(request, "dashboard/map.html", {
            "clusters": clusters,
            "localities": localities_for_template,
            "mapped_count": mapped_count,
            "unmapped_count": unmapped_count,
            "total_count": len(clusters),
            "tile_url": cfg.get("MAP_BASEMAP_TILES", "https://tile.openstreetmap.org/{z}/{x}/{y}.png"),
            "attribution": cfg.get("MAP_BASEMAP_ATTRIBUTION", "© OpenStreetMap contributors"),
            "max_zoom": cfg.get("MAP_MAX_ZOOM", 19),
            "can_request_advisory": bool(request.user.is_authenticated and request.user.is_officer()),
        })


class AuditTrailView(LoginRequiredMixin, View):
    def get(self, request):
        events = AuditEvent.objects.select_related("actor").order_by("-created_at")[:200]
        return render(request, "dashboard/audit.html", {"events": events})
