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
from apps.pests.models import PestAlert
from apps.tasks.models import FollowUpTask
from apps.weather.models import WeatherSignal


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

        weather_summary = WeatherSignal.objects.order_by("-source_date").first()
        pest_summary = PestAlert.objects.order_by("-source_date").first()

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
                "weather_summary": weather_summary,
                "pest_summary": pest_summary,
                "office_name": "Nyatike Sub-County Agricultural Office (intended user)",
                "ward": "Kachieng",
                "sub_county": "Nyatike",
                "county": "Migori",
            },
        )


class ClusterMapView(LoginRequiredMixin, View):
    def get(self, request):
        clusters = list(FarmerCluster.objects.select_related("ward__sub_county__county").all())
        cfg = settings.MAJISHAMBA
        return render(request, "dashboard/map.html", {
            "clusters": clusters,
            "tile_url": cfg.get("MAP_BASEMAP_TILES", "https://tile.openstreetmap.org/{z}/{x}/{y}.png"),
            "attribution": cfg.get("MAP_BASEMAP_ATTRIBUTION", "© OpenStreetMap contributors"),
            "max_zoom": cfg.get("MAP_MAX_ZOOM", 19),
        })


class AuditTrailView(LoginRequiredMixin, View):
    def get(self, request):
        events = AuditEvent.objects.select_related("actor").order_by("-created_at")[:200]
        return render(request, "dashboard/audit.html", {"events": events})
