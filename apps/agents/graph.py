"""LangGraph agent: draft -> validate -> save -> wait for human approval.

The graph is built programmatically with `langgraph.graph.StateGraph`.
It accepts a Kachieng cluster request, gathers evidence through MCP-style
tools (implemented in apps.mcp_tools.tools), drafts an advisory with
Qwen2.5-7B-Instruct via Ollama (or a deterministic fallback), validates
the output against a strict schema, and saves it as DRAFT.

The graph STOPS at the officer_approval_gate node. Approval happens in
the Django UI (apps.approvals). After approval, `create_approved_record`
is run from the approval view, not from the graph.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import time
from typing import Any, Callable

from pydantic import ValidationError

from apps.advisories.models import Advisory, AdvisoryEvidence
from apps.audit.service import log_tool_call
from apps.clusters.models import FarmerCluster
from apps.mcp_tools.tools import (
    create_draft_advisory_record,
    get_cluster_plot_history,
    get_crop_calendar,
    get_pest_alerts,
    get_weather_and_rainfall_context,
    get_market_price_context,
    validate_advisory_evidence,
)

from .schemas import AdvisoryDraft
from .state import AgentState

logger = logging.getLogger("majishamba.agent")


# --- Try to import LangGraph; provide a tiny shim if missing ----------------
try:
    from langgraph.graph import END, START, StateGraph  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - shim for environments without langgraph
    START = "__start__"
    END = "__end__"

    class _ShimEdge:
        def __init__(self, fn) -> None:  # type: ignore[no-untyped-def]
            self.fn = fn

        def __call__(self, state: AgentState) -> AgentState:
            return self.fn(state)

    class StateGraph:  # type: ignore[no-redef]
        """Tiny fallback StateGraph that runs nodes in order.

        Used only if langgraph is not installed. We always list langgraph in
        pyproject.toml, so this branch is dead code in normal installs.
        """

        def __init__(self, state_type: type) -> None:  # noqa: ARG002
            self.nodes: dict[str, Callable] = {}
            self.edges: list[tuple[str, str]] = []
            self.conditionals: list[tuple[str, Callable, dict[str, str]]] = []

        def add_node(self, name: str, fn: Callable) -> None:
            self.nodes[name] = fn

        def add_edge(self, a: str, b: str) -> None:
            self.edges.append((a, b))

        def add_conditional_edges(self, src: str, cond: Callable, mapping: dict[str, str]) -> None:
            self.conditionals.append((src, cond, mapping))

        def compile(self) -> Callable[[AgentState], AgentState]:
            def runner(initial: AgentState) -> AgentState:
                # Walk a straight path from START through nodes following edges.
                state: AgentState = dict(initial)  # type: ignore[assignment]
                # Find START edges first
                order: list[str] = []
                seen: set[str] = set()
                # naive traversal: use first matching edge
                current: str | None = START
                while current:
                    seen.add(current)
                    next_name: str | None = None
                    for (a, b) in self.edges:
                        if a == current and b not in seen:
                            next_name = b
                            break
                    if current == START or next_name is None and current == START:
                        # try first edge from START
                        for (a, b) in self.edges:
                            if a == START:
                                next_name = b
                                break
                    if not next_name or current == END:
                        break
                    if current in self.nodes:
                        state = self.nodes[current](state)  # type: ignore[arg-type]
                    # Check conditional
                    for (src, cond, mapping) in self.conditionals:
                        if src == current:
                            branch = cond(state)
                            next_name = mapping.get(branch, next_name)
                            break
                    current = next_name
                if current in self.nodes:
                    state = self.nodes[current](state)  # type: ignore[arg-type]
                return state

            return runner


# --- Node implementations ---------------------------------------------------

def validate_request(state: AgentState) -> AgentState:
    cluster_id = state.get("cluster_id")
    if not cluster_id:
        return {**state, "errors": [{"node": "validate_request", "msg": "cluster_id required"}]}
    try:
        cluster = FarmerCluster.objects.get(cluster_id=cluster_id)
    except FarmerCluster.DoesNotExist:
        return {**state, "errors": [{"node": "validate_request", "msg": f"Cluster {cluster_id} not found"}]}

    ward = state.get("ward") or cluster.ward.name
    sub_county = state.get("sub_county") or cluster.ward.sub_county.name
    county = state.get("county") or cluster.ward.sub_county.county.name
    return {**state, "ward": ward, "sub_county": sub_county, "county": county, "warnings": []}


def fetch_plot_history(state: AgentState) -> AgentState:
    res = get_cluster_plot_history(
        cluster_id=state["cluster_id"],
        ward=state.get("ward", "Kachieng"),
        sub_county=state.get("sub_county", "Nyatike"),
        county=state.get("county", "Migori"),
    )
    log_tool_call(tool_name="get_cluster_plot_history", inputs={"cluster_id": state["cluster_id"]}, outputs=res)
    return {**state, "plot_history": res.get("plots", []), "warnings": (state.get("warnings") or []) + res.get("warnings", [])}


def fetch_crop_calendar(state: AgentState) -> AgentState:
    res = get_crop_calendar(crop="maize", zone="Migori-Low-Mid", season="short_rains")
    log_tool_call(tool_name="get_crop_calendar", inputs={"crop": "maize", "zone": "Migori-Low-Mid", "season": "short_rains"}, outputs=res)
    return {**state, "crop_calendar": res, "warnings": (state.get("warnings") or []) + res.get("warnings", [])}


def fetch_weather(state: AgentState) -> AgentState:
    res = get_weather_and_rainfall_context(
        sub_county=state.get("sub_county", "Nyatike"),
        period="last_30_days",
    )
    log_tool_call(tool_name="get_weather_and_rainfall_context",
                  inputs={"sub_county": state.get("sub_county", "Nyatike"), "period": "last_30_days"},
                  outputs=res)
    res2 = get_weather_and_rainfall_context(
        sub_county=state.get("sub_county", "Nyatike"),
        period="10_day_forecast",
    )
    log_tool_call(tool_name="get_weather_and_rainfall_context",
                  inputs={"sub_county": state.get("sub_county", "Nyatike"), "period": "10_day_forecast"},
                  outputs=res2)
    return {**state, "weather": {"last_30_days": res, "10_day_forecast": res2},
            "warnings": (state.get("warnings") or []) + res.get("warnings", []) + res2.get("warnings", [])}


def fetch_pest_alerts(state: AgentState) -> AgentState:
    res = get_pest_alerts(crop="maize", county=state.get("county", "Migori"), region="Nyanza")
    log_tool_call(tool_name="get_pest_alerts", inputs={"crop": "maize", "county": state.get("county", "Migori"), "region": "Nyanza"}, outputs=res)
    return {**state, "pest_alerts": res.get("alerts", []), "warnings": (state.get("warnings") or []) + res.get("warnings", [])}


def fetch_market_prices(state: AgentState) -> AgentState:
    res = get_market_price_context(crop="maize", market="Migori-Town")
    log_tool_call(tool_name="get_market_price_context", inputs={"crop": "maize", "market": "Migori-Town"}, outputs=res)
    return {**state, "market_prices": res.get("prices", []), "warnings": (state.get("warnings") or []) + res.get("warnings", [])}


def validate_evidence(state: AgentState) -> AgentState:
    """Use the MCP `validate_advisory_evidence` tool against an empty draft.

    We send the gathered evidence to the validator early to flag gaps before
    we spend a model call drafting prose.
    """
    evidence = [
        {"source_type": "plot_history", "source_ref": state.get("cluster_id", ""), "claim": "Plot history"},
        {"source_type": "crop_calendar", "source_ref": state.get("crop_calendar", {}).get("source", ""), "claim": "Calendar"},
        {"source_type": "weather", "source_ref": state.get("weather", {}).get("last_30_days", {}).get("source", ""), "claim": "Rainfall"},
        {"source_type": "pest", "source_ref": "; ".join(a.get("pest", "") for a in state.get("pest_alerts", [])), "claim": "Pest alerts"},
    ]
    res = validate_advisory_evidence(advisory_draft="", evidence=evidence)
    log_tool_call(tool_name="validate_advisory_evidence", inputs={"evidence_count": len(evidence)}, outputs=res)
    return {**state, "evidence_validation": res,
            "warnings": (state.get("warnings") or []) + res.get("warnings", [])}


def _build_prompt(state: AgentState) -> str:
    """Compose the advisory drafting prompt with citations.

    Kept compact so the model has fewer input tokens to process — important
    when running on CPU where generation is ~2 tokens/second.
    """
    ph = state.get("plot_history", []) or []
    cc = state.get("crop_calendar", {}) or {}
    wx = state.get("weather", {}) or {}
    pa = state.get("pest_alerts", []) or []
    mp = state.get("market_prices", []) or []
    # Compact evidence summaries (truncate aggressively to keep prompt small)
    plot_summary = (
        f"{len(ph)} plots; "
        + "; ".join(
            f"{p.get('plot_id','?')}: {len(p.get('seasons',[]))} seasons" for p in ph[:5]
        )
    ) if ph else "No plot records"
    cc_summary = (
        f"window {cc.get('planting_window_start','?')} to {cc.get('planting_window_end','?')} "
        f"(source: {cc.get('source','?')} {cc.get('source_date','?')})"
    ) if cc else "No calendar"
    wx30 = wx.get("last_30_days", {}) or {}
    wx10 = wx.get("10_day_forecast", {}) or {}
    wx_summary = (
        f"last30: {wx30.get('rainfall_mm','?')}mm onset={wx30.get('onset_status','?')} (src: {wx30.get('source','?')}); "
        f"forecast: {wx10.get('forecast_summary','?')[:120]} (src: {wx10.get('source','?')})"
    )
    pest_summary = "; ".join(
        f"{a.get('pest','?')}({a.get('severity','?')})" for a in pa[:3]
    ) or "No pest alerts"
    market_summary = (
        f"{mp[0].get('price_kes_per_90kg','?')} KES/90kg trend={mp[0].get('trend','?')} (src: {mp[0].get('source','?')})"
        if mp else "No market data"
    )
    return f"""You are a climate-smart agriculture assistant for the Nyatike Sub-County Agricultural Office,
serving smallholder farmer clusters in Kachieng Ward, Migori County, Kenya.
Draft an OFFICER-FACING advisory for cluster {state.get('cluster_id')} for the SHORT RAINS maize season.

Use ONLY the following evidence. Do not invent data.
Respond in strict JSON with fields:
recommendation_type (one of: plant, delay, verify_locally, pest_monitoring, data_gap),
summary (<=240 chars),
body (3-5 paragraphs, with [Source: ...] citations in each paragraph where relevant),
confidence (low/medium/high),
limitations,
evidence (array of {{source_type, source_ref, claim, source_url}}).

EVIDENCE:
- Plot history: {plot_summary}
- Crop calendar: {cc_summary}
- Weather: {wx_summary}
- Pest alerts: {pest_summary}
- Market prices: {market_summary}

Output the JSON object only. Do not add prose outside the JSON."""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _try_ollama(prompt: str) -> dict[str, Any] | None:
    """Try to call Qwen2.5-7B-Instruct via Ollama. Returns metadata + text, or None."""
    try:
        import ollama  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover
        logger.warning("Ollama client not importable: %s", exc)
        return None

    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    timeout_s = int(os.environ.get("MAJISHAMBA_OLLAMA_TIMEOUT", "300"))
    num_predict = int(os.environ.get("MAJISHAMBA_OLLAMA_NUM_PREDICT", "400"))
    keep_alive = os.environ.get("MAJISHAMBA_OLLAMA_KEEP_ALIVE", "10m")
    started = time.time()
    try:
        client = ollama.Client(host=host, timeout=timeout_s)
        resp = client.generate(
            model=model,
            prompt=prompt,
            stream=False,
            keep_alive=keep_alive,
            options={
                "temperature": 0.2,
                "num_predict": num_predict,
                "top_p": 0.9,
            },
        )
        text = (resp.get("response") if isinstance(resp, dict) else getattr(resp, "response", "")) or ""
        return {
            "text": _strip_code_fence(text),
            "model": model,
            "host": host,
            "elapsed_s": round(time.time() - started, 1),
            "num_predict": num_predict,
        }
    except Exception as exc:
        logger.warning("Ollama call failed (%s); will fall back to template.", exc)
        return None


def _fallback_template(state: AgentState) -> str:
    """Deterministic advisory when the model is unavailable or output is invalid."""
    cc = state.get("crop_calendar", {}) or {}
    wx = state.get("weather", {}) or {}
    last30 = wx.get("last_30_days", {}) or {}
    fcst = wx.get("10_day_forecast", {}) or {}
    onset = last30.get("onset_status", "unknown")
    rainfall = last30.get("rainfall_mm")
    pa = state.get("pest_alerts", []) or []

    if state.get("evidence_validation", {}).get("missing_required"):
        rec = "data_gap"
    elif onset == "onset_delayed" or (rainfall is not None and rainfall < 40):
        rec = "delay"
    elif onset == "false_start":
        rec = "verify_locally"
    elif any(a.get("severity") == "high" for a in pa):
        rec = "pest_monitoring"
    else:
        rec = "plant"

    cluster = state.get("cluster_id", "KACH-XX")
    summary = {
        "plant": f"Planting window for {cluster} (short rains maize) is suitable — proceed.",
        "delay": f"Delay planting for {cluster}; verify local rainfall onset before sowing.",
        "verify_locally": f"Rainfall onset for {cluster} looks like a false start — verify locally.",
        "pest_monitoring": f"Set up pest monitoring for {cluster}; fall armyworm risk elevated.",
        "data_gap": f"Evidence gaps for {cluster} — officer follow-up required before advisory.",
    }[rec]

    body_parts = [
        f"Cluster {cluster} (Kachieng Ward, Nyatike Sub-County, Migori County) — short rains maize advisory.",
        f"Planting window from crop calendar: {cc.get('planting_window_start', '?')} to {cc.get('planting_window_end', '?')}. [Source: {cc.get('source', '?')}]",
        f"Last 30 days rainfall: {rainfall} mm with onset status '{onset}'. [Source: {last30.get('source', '?')}]",
        f"10-day forecast: {fcst.get('forecast_summary', 'N/A')}. [Source: {fcst.get('source', '?')}]",
    ]
    if pa:
        body_parts.append(f"Pest alerts: {'; '.join(a['pest']+' ('+a['severity']+')' for a in pa)}. [Source: {pa[0].get('source', '?')}]")
    body_parts.append("Recommendation: officer to verify local rainfall onset in Kachieng with cluster representative before any planting decision.")

    return json.dumps({
        "recommendation_type": rec,
        "summary": summary,
        "body": "\n\n".join(body_parts),
        "confidence": "medium",
        "limitations": "Advisory generated by deterministic fallback — review by officer required.",
        "evidence": [
            {"source_type": "crop_calendar", "source_ref": cc.get("source", ""), "claim": "Planting window", "source_url": cc.get("source_url", "")},
            {"source_type": "weather", "source_ref": last30.get("source", ""), "claim": "Last 30 days rainfall", "source_url": last30.get("source_url", "")},
        ],
    })


def draft_advisory(state: AgentState) -> AgentState:
    """Draft an advisory using Qwen2.5-7B-Instruct via Ollama; fall back to template."""
    prompt = _build_prompt(state)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    out = _try_ollama(prompt)
    if out and out["text"]:
        return {
            **state,
            "raw_model_output": out["text"],
            "generation_mode": "ollama_qwen",
            "model_metadata": {
                "model": out["model"],
                "host": out["host"],
                "elapsed_s": out["elapsed_s"],
                "prompt_hash": prompt_hash,
            },
        }
    # Fallback
    fallback_json = _fallback_template(state)
    return {
        **state,
        "raw_model_output": fallback_json,
        "generation_mode": "fallback_template",
        "model_metadata": {"model": "fallback_template", "prompt_hash": prompt_hash},
    }


def validate_output_schema(state: AgentState) -> AgentState:
    raw = state.get("raw_model_output", "")
    text = _strip_code_fence(raw)
    # Try to extract a JSON object from the text (model may wrap in prose)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find the first {...} block
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                return {**state, "errors": [{"node": "validate_output_schema", "msg": f"JSON parse failed: {exc}"}]}
        else:
            return {**state, "errors": [{"node": "validate_output_schema", "msg": "No JSON found in model output"}]}
    try:
        draft = AdvisoryDraft.model_validate(data)
    except ValidationError as exc:
        return {**state, "errors": [{"node": "validate_output_schema", "msg": str(exc)}]}

    # Stale-source detection
    fresh_warnings = state.get("warnings") or []
    if state.get("crop_calendar", {}).get("is_stale"):
        fresh_warnings.append("Crop calendar source is stale (>2 years).")
        draft = draft.model_copy(update={"confidence": "low", "limitations": (draft.limitations + " Calendar source stale.").strip()})
    return {**state, "draft": draft, "warnings": fresh_warnings}


def save_draft(state: AgentState) -> AgentState:
    """Save the validated draft via the MCP `create_draft_advisory_record` tool."""
    if state.get("errors") or not state.get("draft"):
        return state
    draft = state["draft"]
    evidence_links = [
        {
            "source_type": e.source_type,
            "source_ref": e.source_ref,
            "claim": e.claim,
            "source_url": e.source_url,
            "is_stale": e.is_stale,
        }
        for e in draft.evidence
    ]
    res = create_draft_advisory_record(
        advisory_text=draft.body,
        summary=draft.summary,
        recommendation_type=draft.recommendation_type,
        confidence=draft.confidence,
        limitations=draft.limitations,
        evidence_links=evidence_links,
        model_metadata=state.get("model_metadata", {}),
        cluster_id=state["cluster_id"],
        ward=state.get("ward", "Kachieng"),
        sub_county=state.get("sub_county", "Nyatike"),
        county=state.get("county", "Migori"),
        actor_id=state.get("actor_id"),
    )
    log_tool_call(
        tool_name="create_draft_advisory_record",
        inputs={"cluster_id": state["cluster_id"], "recommendation_type": draft.recommendation_type},
        outputs={"advisory_id": res.get("advisory_id"), "status": res.get("status")},
        approval_status="draft",
    )
    if res.get("advisory_id"):
        return {**state, "advisory_id": res["advisory_id"]}
    return {**state, "errors": [{"node": "save_draft", "msg": res.get("error", "save failed")}]}


def officer_approval_gate(state: AgentState) -> AgentState:
    """Terminal node — waits for the human officer to act in the Django UI."""
    return {**state, "warnings": (state.get("warnings") or []) + ["Advisory saved as DRAFT. Awaiting officer approval."]}


# --- Conditional routing ----------------------------------------------------

def route_after_validate(state: AgentState) -> str:
    if state.get("errors"):
        return "officer_approval_gate"  # stop with errors
    return "fetch_plot_history"


def route_after_save(state: AgentState) -> str:
    if state.get("errors"):
        return "officer_approval_gate"  # saving failed — still terminal but flagged
    return "officer_approval_gate"


def route_after_validate_output(state: AgentState) -> str:
    if state.get("errors"):
        # Try the template fallback once if model output is invalid AND we used ollama
        if state.get("generation_mode") == "ollama_qwen":
            return "draft_advisory"
        return "officer_approval_gate"
    return "save_draft"


def route_after_draft(state: AgentState) -> str:
    # If we already failed once on a template, route to save with the template.
    return "validate_output_schema"


# --- Build the graph --------------------------------------------------------

def build_graph():  # type: ignore[no-untyped-def]
    g = StateGraph(AgentState)  # type: ignore[arg-type]
    g.add_node("validate_request", validate_request)
    g.add_node("fetch_plot_history", fetch_plot_history)
    g.add_node("fetch_crop_calendar", fetch_crop_calendar)
    g.add_node("fetch_weather", fetch_weather)
    g.add_node("fetch_pest_alerts", fetch_pest_alerts)
    g.add_node("fetch_market_prices", fetch_market_prices)
    g.add_node("validate_evidence", validate_evidence)
    g.add_node("draft_advisory", draft_advisory)
    g.add_node("validate_output_schema", validate_output_schema)
    g.add_node("save_draft", save_draft)
    g.add_node("officer_approval_gate", officer_approval_gate)

    g.add_edge(START, "validate_request")
    g.add_conditional_edges("validate_request", route_after_validate, {
        "officer_approval_gate": "officer_approval_gate",
        "fetch_plot_history": "fetch_plot_history",
    })
    g.add_edge("fetch_plot_history", "fetch_crop_calendar")
    g.add_edge("fetch_crop_calendar", "fetch_weather")
    g.add_edge("fetch_weather", "fetch_pest_alerts")
    g.add_edge("fetch_pest_alerts", "fetch_market_prices")
    g.add_edge("fetch_market_prices", "validate_evidence")
    g.add_edge("validate_evidence", "draft_advisory")
    g.add_conditional_edges("draft_advisory", route_after_draft, {
        "validate_output_schema": "validate_output_schema",
    })
    g.add_conditional_edges("validate_output_schema", route_after_validate_output, {
        "draft_advisory": "draft_advisory",
        "save_draft": "save_draft",
        "officer_approval_gate": "officer_approval_gate",
    })
    g.add_conditional_edges("save_draft", route_after_save, {
        "officer_approval_gate": "officer_approval_gate",
    })
    g.add_edge("officer_approval_gate", END)

    return g.compile()
