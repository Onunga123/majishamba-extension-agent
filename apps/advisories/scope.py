"""Scope snapshots for advisories — what the run actually saw."""
from __future__ import annotations

from typing import Any

from django.utils.timezone import now


def build_scope_snapshot(*, plot_history: list[dict], warnings: list[str]) -> dict[str, Any]:
    household_ids: set[str] = set()
    plots_included: list[dict[str, Any]] = []
    for plot in plot_history or []:
        hid = plot.get("household_id") or ""
        if hid:
            household_ids.add(hid)
        seasons = plot.get("seasons") or []
        plots_included.append({
            "plot_id": plot.get("plot_id"),
            "household_id": hid,
            "season_record_count": len(seasons),
            "has_recent_season": bool(seasons),
        })
    missing = [w for w in (warnings or []) if "plot" in w.lower() or "No plot" in w]
    return {
        "captured_at": now().isoformat(),
        "household_count": len(household_ids),
        "plot_count": len(plots_included),
        "household_ids": sorted(household_ids),
        "plots_included": plots_included,
        "missing_or_excluded_notes": missing,
        "note": "Snapshot from this advisory run — not live database totals.",
    }
