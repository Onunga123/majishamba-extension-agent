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


# Status filter choices — also drives the template filter chips.
CLUSTER_STATUS_FILTERS = (
    ("all", "All"),
    ("draft", "Draft"),
    ("approved", "Approved"),
    ("needs_field_visit", "Needs field visit"),
    ("no_advisory", "No advisory yet"),
)


def _latest_real_weather():
    """Return the most recent NON-synthetic, NON-quarantined WeatherSignal, or None.
    Records with verification_status='review_required' are excluded.
    Prioritizes Open-Meteo API weather over manual KMD ingestion (more recent, structured)."""
    return (
        WeatherSignal.objects
        .exclude(synthetic_flag="synthetic")
        .exclude(verification_status="review_required")
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


def _cluster_next_action(cluster, advisory_q):
    """Return a short string describing the next action for a cluster,
    based on its most recent advisory status.

    Returns one of:
        "Request advisory"     — no advisory yet
        "Review draft"         — latest advisory is draft
        "Field visit"          — latest advisory is approved + has follow-up task
        "Re-evidence"          — latest advisory is needs_evidence
        "Reconsider"           — latest advisory is rejected
        "Deferred"             — latest advisory is deferred
        "Approved"             — latest advisory is approved (no pending task)
    """
    latest = advisory_q.order_by("-created_at").first()
    if latest is None:
        return "Request advisory"
    s = latest.status
    if s == Advisory.Status.DRAFT:
        return "Review draft"
    if s == Advisory.Status.APPROVED:
        has_open_task = latest.follow_up_tasks.exclude(
            status__in=[FollowUpTask.Status.COMPLETED, FollowUpTask.Status.VERIFIED,
                        FollowUpTask.Status.CLOSED, FollowUpTask.Status.CANCELLED]
        ).exists()
        return "Field visit" if has_open_task else "Approved"
    if s == Advisory.Status.NEEDS_EVIDENCE:
        return "Re-evidence"
    if s == Advisory.Status.REJECTED:
        return "Reconsider"
    if s == Advisory.Status.DEFERRED:
        return "Deferred"
    return "Review"


def _cluster_filter_to_status(cluster_stats: list[dict], status_filter: str) -> list[dict]:
    """Apply the status filter to the cluster_stats list. 'all' returns everything."""
    if status_filter == "all":
        return cluster_stats
    if status_filter == "draft":
        return [c for c in cluster_stats if c["draft_count"] > 0]
    if status_filter == "approved":
        return [c for c in cluster_stats if c["approved_count"] > 0]
    if status_filter == "needs_field_visit":
        return [c for c in cluster_stats if c["next_action"] == "Field visit"]
    if status_filter == "no_advisory":
        return [c for c in cluster_stats if c["advisory_count"] == 0]
    return cluster_stats


class DashboardHomeView(LoginRequiredMixin, View):
    def get(self, request):
        # --- Search + filter params ---
        search_q = (request.GET.get("q") or "").strip()
        status_filter = request.GET.get("status") or "all"
        if status_filter not in {value for value, _ in CLUSTER_STATUS_FILTERS}:
            status_filter = "all"

        can_request_advisory = bool(request.user.is_authenticated and request.user.is_officer())

        # --- Cluster list (with optional search) ---
        cluster_qs = FarmerCluster.objects.select_related("ward__sub_county__county").all()
        if search_q:
            cluster_qs = cluster_qs.filter(
                Q(name__icontains=search_q) | Q(cluster_id__icontains=search_q) | Q(locality__icontains=search_q)
            )
        clusters = list(cluster_qs)

        cluster_stats = []
        for c in clusters:
            advisory_q = c.advisories.all()
            cluster_stats.append({
                "cluster": c,
                "household_count": c.households.count(),
                "plot_count": sum(h.plots.count() for h in c.households.all()),
                "advisory_count": advisory_q.count(),
                "draft_count": advisory_q.filter(status=Advisory.Status.DRAFT).count(),
                "approved_count": advisory_q.filter(status=Advisory.Status.APPROVED).count(),
                "next_action": _cluster_next_action(c, advisory_q),
                "latest_advisory_status": (
                    advisory_q.order_by("-created_at").first().status if advisory_q.exists() else None
                ),
            })

        # Apply the status filter to cluster_stats (post-aggregation because the
        # 'needs_field_visit' filter depends on next_action which is computed in Python).
        filtered_cluster_stats = _cluster_filter_to_status(cluster_stats, status_filter)

        # --- Recent advisories grouped by status (limit 5–7 each) ---
        recent_advisories_qs = Advisory.objects.select_related("cluster").order_by("-created_at")
        advisories_by_status = {
            "draft": list(recent_advisories_qs.filter(status=Advisory.Status.DRAFT)[:7]),
            "approved": list(recent_advisories_qs.filter(status=Advisory.Status.APPROVED)[:7]),
            "rejected": list(recent_advisories_qs.filter(status=Advisory.Status.REJECTED)[:7]),
        }
        recent_advisories_flat = list(recent_advisories_qs[:7])  # for the "all" fallback

        # --- Pending tasks: short summary, 5 max ---
        pending_tasks = list(
            FollowUpTask.objects
            .exclude(status__in=[FollowUpTask.Status.COMPLETED, FollowUpTask.Status.VERIFIED,
                                  FollowUpTask.Status.CLOSED, FollowUpTask.Status.CANCELLED])
            .select_related("approved_advisory__cluster")
            .order_by("deadline")[:5]
        )

        # --- Recent activity summary (max 5 audit events, decision-oriented) ---
        recent_events = list(
            AuditEvent.objects
            .select_related("actor")
            .exclude(action__startswith="tool:")  # exclude raw tool-call traces from the summary
            .order_by("-created_at")[:5]
        )

        # Badges for the nav and dashboard
        draft_advisory_count = Advisory.objects.filter(status=Advisory.Status.DRAFT).count()
        pending_task_count = FollowUpTask.objects.exclude(
            status__in=[FollowUpTask.Status.COMPLETED, FollowUpTask.Status.VERIFIED,
                         FollowUpTask.Status.CLOSED, FollowUpTask.Status.CANCELLED]
        ).count()

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
                "cluster_stats": filtered_cluster_stats,
                "cluster_count": len(clusters),
                "filtered_cluster_count": len(filtered_cluster_stats),
                "search_q": search_q,
                "status_filter": status_filter,
                "status_filter_choices": CLUSTER_STATUS_FILTERS,
                "advisories_by_status": advisories_by_status,
                "recent_advisories": recent_advisories_flat,
                "recent_events": recent_events,
                "pending_tasks": pending_tasks,
                "draft_advisory_count": draft_advisory_count,
                "pending_task_count": pending_task_count,
                "weather_panel": weather_panel,
                "pest_panel": pest_panel,
                "kalro_state": kalro_state,
                "can_request_advisory": can_request_advisory,
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
        # Substitute API key into tile URL if configured.
        tile_url = cfg.get("MAP_BASEMAP_TILES", "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png")
        api_key = cfg.get("MAP_API_KEY", "")
        if api_key and "{api_key}" in tile_url:
            tile_url = tile_url.replace("{api_key}", api_key)
        # Remove {r} placeholder (retina) — MapLibre raster sources don't support it.
        tile_url = tile_url.replace("{r}", "")
        return render(request, "dashboard/map.html", {
            "clusters": clusters,
            "localities": localities_for_template,
            "mapped_count": mapped_count,
            "unmapped_count": unmapped_count,
            "total_count": len(clusters),
            "tile_url": tile_url,
            "attribution": cfg.get("MAP_BASEMAP_ATTRIBUTION", "© Stadia Maps © OpenMapTiles © OpenStreetMap contributors"),
            "max_zoom": cfg.get("MAP_MAX_ZOOM", 20),
            "can_request_advisory": bool(request.user.is_authenticated and request.user.is_officer()),
        })


class AuditTrailView(LoginRequiredMixin, View):
    def get(self, request):
        events = AuditEvent.objects.select_related("actor").order_by("-created_at")[:200]
        return render(request, "dashboard/audit.html", {"events": events})


class AboutView(LoginRequiredMixin, View):
    """About / Legal page — moved off the main dashboard.
    Contains the long explanatory paragraph about the agent's pipeline,
    MIT licence details, and detailed legal text.
    """

    def get(self, request):
        return render(request, "dashboard/about.html", {})


class GuidanceView(LoginRequiredMixin, View):
    """Dedicated Guidance page — KALRO permission pending details,
    bibliographic record, extraction deferral, and link to KALRO publication.
    Moved off the main dashboard.
    """

    def get(self, request):
        kalro_state = kalro_permission_status()
        return render(request, "dashboard/guidance.html", {"kalro_state": kalro_state})


class DataSourcesView(LoginRequiredMixin, View):
    """Data sources page — detailed notes on weather, pest, and market
    source authorities, plus the synthetic-data disclaimer.
    Moved off the main dashboard.
    """

    def get(self, request):
        weather_no_notice = no_current_kmd_notice()
        pest_no_notice = no_current_pest_notice()
        synthetic_weather = _latest_synthetic_weather()
        synthetic_pest = _latest_synthetic_pest_notice()
        return render(
            request,
            "dashboard/data_sources.html",
            {
                "weather_no_notice": weather_no_notice,
                "pest_no_notice": pest_no_notice,
                "synthetic_weather": synthetic_weather,
                "synthetic_pest": synthetic_pest,
                "demo_mode": bool(settings.MAJISHAMBA.get("DEMO_MODE", False)) and bool(settings.DEBUG),
            },
        )
