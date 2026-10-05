"""The custom MCP server's tool implementations.

These functions are the SINGLE SOURCE OF TRUTH for tool behaviour. They are
called from three places:

  1. The LangGraph agent (apps.agents.graph) — directly imported.
  2. The Django UI / approval views — via the service layer.
  3. The standalone MCP server (apps.mcp_tools.server) — exposed over stdio
     using the official MCP Python SDK.

Each tool logs every call to AuditEvent with sanitised inputs and a summary
output. Action tools (create_draft_advisory_record,
create_follow_up_task_after_approval) additionally enforce approval gates.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Any

from apps.advisories.models import Advisory, AdvisoryEvidence
from apps.audit.service import log_tool_call
from apps.calendars.models import CropCalendar
from apps.clusters.models import FarmerCluster, Household
from apps.markets.models import MarketPriceSignal
from apps.pests.models import PestAlert
from apps.plots.models import CropSeasonRecord, Plot
from apps.tasks.service import create_follow_up_task_after_approval
from apps.weather.models import WeatherSignal

logger = logging.getLogger("majishamba.mcp_tools")


_INJECT_RE = re.compile(r"\b(ignore|disregard|forget|new instructions?|system prompt)\b", re.IGNORECASE)


def _sanitize_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Strip patterns that look like prompt-injection attempts from text fields."""
    safe: dict[str, Any] = {}
    for k, v in inputs.items():
        if isinstance(v, str):
            v = _INJECT_RE.sub("[redacted]", v)
        elif isinstance(v, dict):
            v = _sanitize_inputs(v)
        elif isinstance(v, list):
            v = [_sanitize_inputs({"i": i})["i"] for i in v]
        safe[k] = v
    return safe


# --- Tool 1: get_cluster_plot_history -----------------------------------

def get_cluster_plot_history(
    *, cluster_id: str, ward: str = "Kachieng", sub_county: str = "Nyatike", county: str = "Migori",
) -> dict[str, Any]:
    """List plots and crop season records for a Kachieng cluster."""
    inputs = {"cluster_id": cluster_id, "ward": ward, "sub_county": sub_county, "county": county}
    inputs = _sanitize_inputs(inputs)
    warnings: list[str] = []
    try:
        cluster = FarmerCluster.objects.select_related("ward__sub_county__county").get(cluster_id=cluster_id)
    except FarmerCluster.DoesNotExist:
        warnings.append(f"Cluster {cluster_id} not found.")
        log_tool_call(tool_name="get_cluster_plot_history", inputs=inputs, outputs={"warnings": warnings})
        return {"cluster_id": cluster_id, "plots": [], "warnings": warnings}

    plots_qs = Plot.objects.filter(household__cluster=cluster).prefetch_related("season_records")
    if not plots_qs.exists():
        warnings.append(f"No plot records found for cluster {cluster_id}.")

    plot_list: list[dict[str, Any]] = []
    for plot in plots_qs:
        seasons = [
            {
                "season": s.season,
                "crop": s.crop,
                "planting_date": s.planting_date.isoformat() if s.planting_date else None,
                "outcome": s.outcome,
                "yield_band": s.yield_band,
            }
            for s in plot.season_records.all()
        ]
        plot_list.append({
            "plot_id": plot.plot_id,
            "household_id": plot.household.household_id,
            "area_ha": plot.area_ha,
            "soil_type": plot.soil_type,
            "irrigation": plot.irrigation,
            "seasons": seasons,
        })
    out = {
        "cluster_id": cluster.cluster_id,
        "cluster_name": cluster.name,
        "ward": cluster.ward.name,
        "sub_county": cluster.ward.sub_county.name,
        "county": cluster.ward.sub_county.county.name,
        "plots": plot_list,
        "warnings": warnings,
    }
    log_tool_call(tool_name="get_cluster_plot_history", inputs=inputs, outputs={"count": len(plot_list), "warnings": warnings})
    return out


# --- Tool 2: get_crop_calendar ------------------------------------------

def get_crop_calendar(*, crop: str = "maize", zone: str = "Migori-Low-Mid", season: str = "short_rains") -> dict[str, Any]:
    inputs = _sanitize_inputs({"crop": crop, "zone": zone, "season": season})
    warnings: list[str] = []
    cc = (
        CropCalendar.objects.filter(crop=crop, season=season)
        .filter(zone_label=zone)
        .order_by("-source_date")
        .first()
    )
    if not cc:
        cc = CropCalendar.objects.filter(crop=crop, season=season).order_by("-source_date").first()
    if not cc:
        warnings.append(f"No crop calendar for crop={crop}, zone={zone}, season={season}.")
        log_tool_call(tool_name="get_crop_calendar", inputs=inputs, outputs={"warnings": warnings})
        return {"crop": crop, "zone": zone, "season": season, "warnings": warnings}

    is_stale = cc.is_stale()
    if is_stale:
        warnings.append(f"Crop calendar source is stale (last update {cc.source_date}).")

    out = {
        "crop": cc.crop,
        "zone": cc.zone_label or (cc.zone.code if cc.zone else zone),
        "season": cc.season,
        "planting_window_start": cc.planting_window_start.isoformat(),
        "planting_window_end": cc.planting_window_end.isoformat(),
        "activities": cc.activities,
        "source": cc.source,
        "source_url": cc.source_url,
        "source_date": cc.source_date.isoformat(),
        "is_stale": is_stale,
        "warnings": warnings,
    }
    log_tool_call(tool_name="get_crop_calendar", inputs=inputs, outputs={"source": out["source"], "is_stale": is_stale})
    return out


# --- Tool 3: get_weather_and_rainfall_context ---------------------------

def get_weather_and_rainfall_context(*, sub_county: str = "Nyatike", period: str = "last_30_days") -> dict[str, Any]:
    inputs = _sanitize_inputs({"sub_county": sub_county, "period": period})
    warnings: list[str] = []
    qs = WeatherSignal.objects.filter(area_label__icontains=sub_county, period=period).order_by("-source_date", "-retrieved_at")
    sig = qs.first()
    if not sig:
        # Fall back to any area_label with the right period.
        sig = WeatherSignal.objects.filter(period=period).order_by("-source_date").first()
    if not sig:
        warnings.append(f"No weather signal for sub_county={sub_county}, period={period}.")
        log_tool_call(tool_name="get_weather_and_rainfall_context", inputs=inputs, outputs={"warnings": warnings})
        return {"sub_county": sub_county, "period": period, "warnings": warnings}

    fresh = sig.is_fresh()
    if not fresh:
        warnings.append(f"Weather signal is stale (retrieved {sig.retrieved_at.isoformat()}).")
    if sig.onset_status not in {"onset_confirmed", "onset_delayed", "false_start", "unknown", ""}:
        warnings.append(f"Unexpected onset_status value: {sig.onset_status!r}")

    out = {
        "sub_county": sub_county,
        "period": period,
        "rainfall_mm": sig.rainfall_mm,
        "forecast_summary": sig.forecast_summary,
        "onset_status": sig.onset_status,
        "confidence": sig.confidence,
        "source": sig.source,
        "source_url": sig.source_url,
        "source_date": sig.source_date.isoformat(),
        "retrieved_at": sig.retrieved_at.isoformat(),
        "is_fresh": fresh,
        "warnings": warnings,
    }
    log_tool_call(tool_name="get_weather_and_rainfall_context", inputs=inputs, outputs={"source": out["source"], "is_fresh": fresh})
    return out


# --- Tool 4: get_pest_alerts --------------------------------------------

def get_pest_alerts(*, crop: str = "maize", county: str = "Migori", region: str = "Nyanza") -> dict[str, Any]:
    inputs = _sanitize_inputs({"crop": crop, "county": county, "region": region})
    qs = PestAlert.objects.filter(crop=crop, county__iexact=county).order_by("-source_date")
    alerts = list(qs[:5])
    warnings: list[str] = []
    if not alerts:
        warnings.append(f"No pest alerts for crop={crop}, county={county}.")
    out = {
        "crop": crop,
        "county": county,
        "region": region,
        "alerts": [
            {
                "pest": a.pest,
                "severity": a.severity,
                "advisory": a.advisory,
                "source": a.source,
                "source_url": a.source_url,
                "source_date": a.source_date.isoformat(),
            }
            for a in alerts
        ],
        "warnings": warnings,
    }
    log_tool_call(tool_name="get_pest_alerts", inputs=inputs, outputs={"count": len(alerts)})
    return out


# --- Tool 5: get_market_price_context -----------------------------------

def get_market_price_context(*, crop: str = "maize", market: str = "Migori-Town") -> dict[str, Any]:
    inputs = _sanitize_inputs({"crop": crop, "market": market})
    qs = MarketPriceSignal.objects.filter(crop=crop, market__iexact=market).order_by("-observation_date")
    prices = list(qs[:5])
    warnings: list[str] = []
    if not prices:
        warnings.append(f"No market prices for crop={crop}, market={market}.")
    trend = prices[0].trend if prices else "unknown"
    out = {
        "crop": crop,
        "market": market,
        "trend": trend,
        "prices": [
            {
                "observation_date": p.observation_date.isoformat(),
                "price_kes_per_90kg": p.price_kes_per_90kg,
                "trend": p.trend,
                "source": p.source,
            }
            for p in prices
        ],
        "warnings": warnings,
    }
    log_tool_call(tool_name="get_market_price_context", inputs=inputs, outputs={"count": len(prices), "trend": trend})
    return out


# --- Tool 6: validate_advisory_evidence ---------------------------------

def validate_advisory_evidence(*, advisory_draft: str, evidence: list[dict]) -> dict[str, Any]:
    inputs = _sanitize_inputs({"draft_chars": len(advisory_draft), "evidence_count": len(evidence)})
    warnings: list[str] = []
    required = {"plot_history", "crop_calendar", "weather"}
    found = {e.get("source_type", "") for e in evidence}
    missing_required = list(required - found)
    if missing_required:
        warnings.append(f"Missing required evidence types: {missing_required}")

    stale: list[str] = []
    for e in evidence:
        if e.get("is_stale"):
            stale.append(e.get("source_ref") or "")
    if stale:
        warnings.append(f"Stale sources flagged: {stale[:3]}")

    valid = not missing_required
    out = {
        "valid": valid,
        "missing_required": missing_required,
        "stale_sources": stale,
        "warnings": warnings,
    }
    log_tool_call(tool_name="validate_advisory_evidence", inputs=inputs, outputs={"valid": valid, "warnings": warnings})
    return out


# --- Tool 7 (action): create_draft_advisory_record ---------------------

def create_draft_advisory_record(
    *,
    advisory_text: str,
    summary: str,
    recommendation_type: str,
    confidence: str,
    limitations: str,
    evidence_links: list[dict],
    model_metadata: dict,
    cluster_id: str,
    ward: str = "Kachieng",
    sub_county: str = "Nyatike",
    county: str = "Migori",
    actor_id: int | None = None,
) -> dict[str, Any]:
    """ACTION TOOL: create a DRAFT advisory record. No external message is sent."""
    inputs = _sanitize_inputs({
        "cluster_id": cluster_id, "recommendation_type": recommendation_type,
        "evidence_count": len(evidence_links), "model_name": model_metadata.get("model", ""),
    })
    try:
        cluster = FarmerCluster.objects.get(cluster_id=cluster_id)
    except FarmerCluster.DoesNotExist:
        out = {"error": f"Cluster {cluster_id} not found."}
        log_tool_call(tool_name="create_draft_advisory_record", inputs=inputs, outputs=out, approval_status="rejected")
        return out

    advisory = Advisory.objects.create(
        cluster=cluster,
        recommendation_type=recommendation_type,
        status=Advisory.Status.DRAFT,
        summary=summary,
        body=advisory_text,
        confidence=confidence,
        limitations=limitations,
        county=county,
        sub_county=sub_county,
        ward=ward,
        model_name=model_metadata.get("model", ""),
        model_run_id=model_metadata.get("prompt_hash", ""),
        model_prompt_hash=model_metadata.get("prompt_hash", ""),
        generation_mode=model_metadata.get("model", "").startswith("qwen") and "ollama_qwen" or "fallback_template",
        created_by_id=actor_id,
    )
    for ev in evidence_links:
        AdvisoryEvidence.objects.create(
            advisory=advisory,
            source_type=ev.get("source_type", "other"),
            source_ref=ev.get("source_ref", ""),
            claim=ev.get("claim", ""),
            is_stale=bool(ev.get("is_stale", False)),
            source_url=ev.get("source_url", ""),
        )
    out = {"advisory_id": advisory.id, "status": advisory.status, "cluster_id": cluster.cluster_id}
    log_tool_call(
        tool_name="create_draft_advisory_record",
        inputs=inputs,
        outputs=out,
        approval_status="draft",
    )
    return out


# --- Tool 8 (action, approval-gated): create_follow_up_task_after_approval

def create_follow_up_task_after_approval(
    *,
    approved_advisory_id: int,
    officer_id: int,
    task_type: str,
    deadline: str | None = None,
    ward: str = "Kachieng",
    actor=None,
) -> dict[str, Any]:
    """Approval-gated action tool. Delegates to apps.tasks.service."""
    inputs = _sanitize_inputs({
        "approved_advisory_id": approved_advisory_id,
        "officer_id": officer_id,
        "task_type": task_type,
        "ward": ward,
    })
    from apps.tasks.service import (
        create_follow_up_task_after_approval as _impl,
    )
    out = _impl(
        approved_advisory_id=approved_advisory_id,
        officer_id=officer_id,
        task_type=task_type,
        deadline=deadline,
        ward=ward,
        actor=actor,
    )
    approval_status = "approved" if out.get("task_id") else "blocked"
    log_tool_call(
        tool_name="create_follow_up_task_after_approval",
        inputs=inputs,
        outputs=out,
        approval_status=approval_status,
    )
    return out


# (kept for backward compatibility — no alias shadowing)
create_follow_up_task_after_approval_tool = create_follow_up_task_after_approval


# --- Helper: list all tool metadata (used by the MCP server) ----------

TOOL_REGISTRY = {
    "get_cluster_plot_history": {
        "fn": get_cluster_plot_history,
        "description": "List plots and crop season records for a Kachieng farmer cluster.",
        "required": ["cluster_id"],
        "optional": ["ward", "sub_county", "county"],
    },
    "get_crop_calendar": {
        "fn": get_crop_calendar,
        "description": "Get the recommended planting window for a crop in a Migori zone/season.",
        "required": [],
        "optional": ["crop", "zone", "season"],
    },
    "get_weather_and_rainfall_context": {
        "fn": get_weather_and_rainfall_context,
        "description": "Get rainfall and forecast signals for Nyatike sub-county.",
        "required": [],
        "optional": ["sub_county", "period"],
    },
    "get_pest_alerts": {
        "fn": get_pest_alerts,
        "description": "Get active pest alerts for a crop in Migori County (Nyanza).",
        "required": [],
        "optional": ["crop", "county", "region"],
    },
    "get_market_price_context": {
        "fn": get_market_price_context,
        "description": "Get recent maize price signals at Migori Town market.",
        "required": [],
        "optional": ["crop", "market"],
    },
    "validate_advisory_evidence": {
        "fn": validate_advisory_evidence,
        "description": "Validate that an advisory cites the required evidence and is not stale.",
        "required": ["evidence"],
        "optional": ["advisory_draft"],
    },
    "create_draft_advisory_record": {
        "fn": create_draft_advisory_record,
        "description": "ACTION: persist a DRAFT advisory record. Officer approval still required afterwards.",
        "required": ["advisory_text", "summary", "recommendation_type", "evidence_links", "cluster_id", "model_metadata"],
        "optional": ["ward", "sub_county", "county", "actor_id"],
    },
    "create_follow_up_task_after_approval": {
        "fn": create_follow_up_task_after_approval_tool,
        "description": "ACTION (approval-gated): create a follow-up task. Requires a valid APPROVED OfficerApproval.",
        "required": ["approved_advisory_id", "officer_id", "task_type"],
        "optional": ["deadline", "ward"],
    },
}
