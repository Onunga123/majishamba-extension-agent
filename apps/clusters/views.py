"""Read-only cluster views for officers."""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, render
from django.views import View

from apps.advisories.models import Advisory

from .models import FarmerCluster


class ClusterDetailView(LoginRequiredMixin, View):
    def get(self, request, cluster_id: str):
        cluster = get_object_or_404(
            FarmerCluster.objects.select_related("ward__sub_county__county"),
            cluster_id=cluster_id,
        )
        households = cluster.households.prefetch_related("plots__season_records").all()
        advisories = Advisory.objects.filter(cluster=cluster).order_by("-created_at")[:10]
        return render(
            request,
            "clusters/detail.html",
            {
                "cluster": cluster,
                "households": households,
                "recent_advisories": advisories,
            },
        )
