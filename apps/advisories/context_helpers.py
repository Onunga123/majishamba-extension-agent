"""Shared template context for advisory review surfaces."""
from __future__ import annotations

from typing import Any

from .display import confidence_explanation, generation_mode_label
from .models import Advisory


def advisory_review_context(advisory: Advisory) -> dict[str, Any]:
    cluster = advisory.cluster
    locality = cluster.locality or cluster.name
    title = f"{locality} — {cluster.cluster_id}"
    if cluster.name and cluster.name not in title:
        title = f"{cluster.name} — {cluster.cluster_id}"

    scope = advisory.scope_snapshot or {}
    return {
        "advisory_title": title,
        "locality_name": cluster.locality,
        "generation_label": generation_mode_label(advisory),
        "confidence_help": confidence_explanation(advisory.confidence),
        "scope_snapshot": scope,
        "is_internal_review": True,
        "crop_label": advisory.crop.replace("_", " ").title(),
        "season_label": advisory.season.replace("_", " ").title(),
    }
