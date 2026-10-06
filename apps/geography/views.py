"""Views for the geography app — locality coordinate management."""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View

from apps.clusters.models import FarmerCluster
from apps.geography.models import LocalityCoordinate


class LocalityListJSONView(LoginRequiredMixin, View):
    """Return all localities as JSON for the map page's JS to consume.

    Only approved LocalityCoordinate entries get real coordinates.
    Synthetic cluster centroids are excluded from the real marker layer.
    """

    def get(self, request: HttpRequest) -> JsonResponse:
        clusters = FarmerCluster.objects.select_related("locality_coordinate").all()
        features: list[dict] = []
        for c in clusters:
            has_coord = (
                hasattr(c, "locality_coordinate")
                and c.locality_coordinate.verification_status == "approved"
                and c.locality_coordinate.coordinate_type != "synthetic"
            )
            if has_coord:
                lc = c.locality_coordinate
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lc.longitude, lc.latitude],  # GeoJSON: [lng, lat]
                    },
                    "properties": {
                        "cluster_id": c.cluster_id,
                        "name": c.name,
                        "locality": c.locality or lc.locality_name,
                        "coordinate_type": lc.coordinate_type,
                        "coordinate_source": lc.coordinate_source,
                        "source_url": lc.source_url,
                        "households": c.households.count(),
                        "verified_by": lc.verified_by,
                        "verified_at": lc.verified_at.isoformat() if lc.verified_at else None,
                        "has_real_coords": True,
                    },
                })
            else:
                features.append({
                    "type": "Feature",
                    "geometry": None,
                    "properties": {
                        "cluster_id": c.cluster_id,
                        "name": c.name,
                        "locality": c.locality or "",
                        "households": c.households.count(),
                        "has_real_coords": False,
                        "notes": "Coordinates not yet recorded" if not hasattr(c, "locality_coordinate") else f"Awaiting review (status: {c.locality_coordinate.verification_status})",
                    },
                })
        return JsonResponse({"type": "FeatureCollection", "features": features})
