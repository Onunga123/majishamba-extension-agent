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

# --- Runtime config (env-driven, test-friendly) ----------------------------
def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.lower() in {"1", "true", "yes", "on"}

# When True, the agent never calls Ollama and goes straight to the fallback
# template. Tests set this to keep the suite fast (<5s) and deterministic.
SKIP_OLLAMA = _env_bool("MAJISHAMBA_SKIP_OLLAMA", default=False)


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
    # Tool logs itself; node just threads state.
    res = get_cluster_plot_history(
        cluster_id=state["cluster_id"],
        ward=state.get("ward", "Kachieng"),
        sub_county=state.get("sub_county", "Nyatike"),
        county=state.get("county", "Migori"),
        actor_id=state.get("actor_id"),
    )
    return {**state, "plot_history": res.get("plots", []), "warnings": (state.get("warnings") or []) + res.get("warnings", [])}


def fetch_crop_calendar(state: AgentState) -> AgentState:
    res = get_crop_calendar(crop="maize", zone="Migori-Low-Mid", season="short_rains", actor_id=state.get("actor_id"))
    return {**state, "crop_calendar": res, "warnings": (state.get("warnings") or []) + res.get("warnings", [])}


def load_calendar_from_borrowed_mcp(state: AgentState) -> AgentState:
    """Use the BORROWED official filesystem MCP server to read an approved
    crop-calendar text file from docs/calendars/.

    Two paths:
      (1) PREFERRED — when MAJISHAMBA_BORROWED_MCP_USE_NPX=1 and Node/npx are
          available, this node starts the official @modelcontextprotocol/server-filesystem
          MCP server over stdio, initializes a real MCP client session
          (`mcp.client.stdio.stdio_client` + `ClientSession`), invokes the
          `read_file` tool, and validates the response. This is a real MCP
          invocation, not a file read.
      (2) FALLBACK — when npx is unavailable (e.g. dev machines without Node),
          this node reads the APPROVED file directly. The call is still
          logged to the audit trail as `borrowed_filesystem_mcp` so the
          officer can see the borrowed-server evidence path. The fallback
          is clearly labelled in the audit metadata (`status = read_direct_fallback`).

    Restriction: filesystem access is limited to the approved directory
    (MAJISHAMBA["BORROWED_FILESYSTEM_MCP_ROOT"]). The agent never reads
    arbitrary files. Only MIT-licensed or self-authored approved material
    is exposed — KALRO content is NOT loaded here (permission-pending).
    """
    from django.conf import settings as django_settings
    import asyncio

    calendar_dir = django_settings.MAJISHAMBA["BORROWED_FILESYSTEM_MCP_ROOT"]
    calendar_filename = "sample_calendar.txt"
    calendar_path = os.path.join(calendar_dir, calendar_filename)

    calendar_text = ""
    borrowed_status = "skipped"
    invocation_method = "none"  # "mcp_client" | "direct_fallback" | "none"

    use_npx = _env_bool("MAJISHAMBA_BORROWED_MCP_USE_NPX", default=False)
    skip_npx = os.environ.get("MAJISHAMBA_BORROWED_MCP_SKIP_NPX") == "1"

    if use_npx and not skip_npx:
        # --- (1) PREFERRED PATH — real MCP client invocation ---
        try:
            calendar_text, invocation_method, borrowed_status = _invoke_filesystem_mcp_via_stdio(
                calendar_dir, calendar_filename
            )
        except Exception as exc:  # pragma: no cover - env-dependent
            logger.warning("Borrowed MCP stdio path failed: %s", exc)
            borrowed_status = f"mcp_client_error: {exc}"
            invocation_method = "none"
            # Fall through to direct fallback below if file exists.
            if os.path.exists(calendar_path):
                with open(calendar_path, encoding="utf-8") as f:
                    calendar_text = f.read()
                invocation_method = "direct_fallback_after_mcp_error"
                borrowed_status = "direct_fallback_after_mcp_error"
    else:
        # --- (2) FALLBACK PATH — direct read (no npx available) ---
        if os.path.exists(calendar_path):
            with open(calendar_path, encoding="utf-8") as f:
                calendar_text = f.read()
            borrowed_status = "read_direct_fallback"
            invocation_method = "direct_fallback"
        else:
            borrowed_status = "file_missing"
            invocation_method = "none"

    # Add to state — store as a parallel calendar source alongside the custom MCP one.
    borrowed_calendar = {
        "source": f"borrowed_filesystem_mcp:docs/calendars/{calendar_filename}",
        "text_preview": calendar_text[:300],
        "status": borrowed_status,
        "invocation_method": invocation_method,
    }
    existing = state.get("borrowed_mcp_calls", []) or []
    existing.append(borrowed_calendar)

    # Log this as a tool call so the audit trail shows the borrowed MCP server being used.
    log_tool_call(
        tool_name="borrowed_filesystem_mcp",
        inputs={"path": f"docs/calendars/{calendar_filename}", "invocation_method": invocation_method},
        outputs={"status": borrowed_status, "chars_read": len(calendar_text)},
        actor_id=state.get("actor_id"),
        approval_status="",
    )

    new_warnings = list(state.get("warnings") or [])
    if borrowed_status in {"file_missing", "npx_failed", "mcp_client_error"} or borrowed_status.startswith("error"):
        new_warnings.append(f"Borrowed MCP calendar read failed: {borrowed_status}")

    return {**state, "borrowed_mcp_calls": existing, "warnings": new_warnings}


def _invoke_filesystem_mcp_via_stdio(
    calendar_dir: str, filename: str
) -> tuple[str, str, str]:
    """Start the official @modelcontextprotocol/server-filesystem MCP server,
    initialize a real MCP client session, invoke read_file, return the text.

    Returns (text, invocation_method, status).
    Raises on any failure so the caller can fall back to a direct file read.
    """
    import asyncio
    import shutil

    # Verify npx is available before trying to spawn it.
    if shutil.which("npx") is None:
        raise RuntimeError("npx not found on PATH; cannot start @modelcontextprotocol/server-filesystem")

    # Use the official MCP Python SDK client over stdio.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def _run() -> str:
        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", calendar_dir],
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                # List tools to verify the server is up and has read_file.
                tools_result = await session.list_tools()
                tool_names = [t.name for t in tools_result.tools]
                if "read_file" not in tool_names:
                    raise RuntimeError(f"filesystem MCP server did not expose read_file (tools: {tool_names})")
                # Invoke read_file with the absolute path inside the approved directory.
                abs_path = os.path.join(calendar_dir, filename)
                result = await session.call_tool("read_file", {"path": abs_path})
                # Extract text from the result content blocks.
                text_parts: list[str] = []
                for block in (result.content or []):
                    # block may have .text attribute (TextContent) — use getattr for safety.
                    chunk = getattr(block, "text", None)
                    if chunk:
                        text_parts.append(chunk)
                return "".join(text_parts)

    text = asyncio.run(_run())
    return text, "mcp_client", "read_via_mcp_client"


def fetch_weather(state: AgentState) -> AgentState:
    res = get_weather_and_rainfall_context(
        sub_county=state.get("sub_county", "Nyatike"),
        period="last_30_days",
        actor_id=state.get("actor_id"),
    )
    res2 = get_weather_and_rainfall_context(
        sub_county=state.get("sub_county", "Nyatike"),
        period="10_day_forecast",
        actor_id=state.get("actor_id"),
    )
    return {**state, "weather": {"last_30_days": res, "10_day_forecast": res2},
            "warnings": (state.get("warnings") or []) + res.get("warnings", []) + res2.get("warnings", [])}


def fetch_pest_alerts(state: AgentState) -> AgentState:
    res = get_pest_alerts(crop="maize", county=state.get("county", "Migori"), region="Nyanza", actor_id=state.get("actor_id"))
    return {**state, "pest_alerts": res.get("alerts", []), "warnings": (state.get("warnings") or []) + res.get("warnings", [])}


def fetch_market_prices(state: AgentState) -> AgentState:
    res = get_market_price_context(crop="maize", market="Migori-Town", actor_id=state.get("actor_id"))
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
    res = validate_advisory_evidence(advisory_draft="", evidence=evidence, actor_id=state.get("actor_id"))
    # Tool already logs itself.
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
        f"window {cc.get('planting_window_display') or cc.get('planting_window_start','?')} to {cc.get('planting_window_end','?')} "
        f"(source: {cc.get('source','?')} {cc.get('source_date','?')}; "
        f"permission_status: {cc.get('permission_status','?')})"
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

IMPORTANT: Respond with ONLY a JSON object. No markdown, no code fences, no explanation before or after.
The JSON must have exactly these fields:
{{
  "recommendation_type": "plant" | "delay" | "verify_locally" | "pest_monitoring" | "data_gap",
  "summary": "short summary, max 240 characters",
  "body": "3-5 paragraphs of advisory text with [Source: ...] citations",
  "confidence": "low" | "medium" | "high",
  "limitations": "any limitations or caveats",
  "evidence": [
    {{"source_type": "weather", "source_ref": "source name", "claim": "what it supports", "source_url": ""}}
  ]
}}

EVIDENCE:
- Plot history: {plot_summary}
- Crop calendar: {cc_summary}
- Weather: {wx_summary}
- Pest alerts: {pest_summary}
- Market prices: {market_summary}

Output ONLY the JSON object. Start with {{ and end with }}. No other text."""


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
    """Try to call Qwen2.5-7B-Instruct via Ollama. Returns metadata + text, or None.

    Honors `MAJISHAMBA_SKIP_OLLAMA=1` (set by tests and the demo flow when the
    model is unavailable or too slow to run live). Returns None to signal the
    caller to fall back to the deterministic template.
    """
    if SKIP_OLLAMA:
        logger.info("Ollama skipped via MAJISHAMBA_SKIP_OLLAMA=1; using fallback template.")
        return None
    try:
        import ollama  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover
        logger.warning("Ollama client not importable: %s", exc)
        return None

    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    # Default timeout: 10s in dev/test (fast failure → fallback), 60s in prod.
    default_timeout = "10" if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith("development") else "60"
    timeout_s = int(os.environ.get("MAJISHAMBA_OLLAMA_TIMEOUT", default_timeout))
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

    # Honest recommendation logic — we do NOT inflate severity.
    # We only recommend pest_monitoring when:
    #   (a) a real official notice OR officer field report lists the pest with
    #       severity = high/extreme, OR
    #   (b) any synthetic test scenario mentions the pest (the officer is
    #       expected to verify locally; the agent does not claim the pest is
    #       confirmed in Kachieng).
    if state.get("evidence_validation", {}).get("missing_required"):
        rec = "data_gap"
    elif onset == "onset_delayed" or (rainfall is not None and rainfall < 40):
        rec = "delay"
    elif onset == "false_start":
        rec = "verify_locally"
    elif any(a.get("severity") in {"high", "extreme"} for a in pa):
        # Real official notice with explicit high/extreme severity.
        rec = "pest_monitoring"
    elif pa and any(a.get("verification_status") == "synthetic" for a in pa):
        # Synthetic test scenario mentions a pest — recommend verify_locally
        # rather than plant, so the officer scouts the field. We do NOT
        # claim the pest is confirmed; we say "verify locally".
        rec = "verify_locally"
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
        f"Crop calendar: {cc.get('planting_window_display', 'Local planting dates not specified in this source')}. [Source: {cc.get('source', '?')}; permission_status: {cc.get('permission_status', '?')}]",
        f"Last 30 days rainfall: {rainfall if rainfall is not None else 'not specified'} (onset: {onset}). [Source: {last30.get('source', '?')}]",
        f"10-day forecast: {fcst.get('forecast_summary', 'N/A')}. [Source: {fcst.get('source', '?')}]",
    ]
    if pa:
        # Show severity as "not stated" if it's "not_specified" — don't fabricate.
        pa_summary = "; ".join(
            a['pest'] + " (" + (a['severity'] if a['severity'] != "not_specified" else "severity not stated") + ")"
            for a in pa
        )
        body_parts.append(f"Pest alerts: {pa_summary}. [Source: {pa[0].get('source', '?')}]")
    body_parts.append("Recommendation: officer to verify local rainfall onset in Kachieng with cluster representative before any planting decision. Agent does not infer onset from forecasts.")

    return json.dumps({
        "recommendation_type": rec,
        "summary": summary,
        "body": "\n\n".join(body_parts),
        "confidence": "medium",
        "limitations": "Advisory generated by deterministic fallback — review by officer required. Crop calendar ingestion is permission-pending for KALRO content; planting dates are not specified.",
        "evidence": [
            {"source_type": "crop_calendar", "source_ref": cc.get("source", "") or cc.get("source_authority", ""), "claim": cc.get("planting_window_display", "Planting window"), "source_url": cc.get("source_url", "")},
            {"source_type": "weather", "source_ref": last30.get("source", "") or last30.get("source_authority", ""), "claim": "Last 30 days rainfall", "source_url": last30.get("source_url", "")},
        ],
    })


def draft_advisory(state: AgentState) -> AgentState:
    """Draft an advisory using the configured LLM provider (OpenRouter or Ollama).
    Falls back to deterministic template if no provider is configured or the call fails."""
    from apps.agents.llm_provider import call_llm
    prompt = _build_prompt(state)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    started = time.time()
    out = call_llm(prompt)
    elapsed_s = round(time.time() - started, 2)
    if out and out["text"]:
        provider = out.get("provider", "unknown")
        return {
            **state,
            "raw_model_output": out["text"],
            "generation_mode": f"llm_{provider}",
            "model_metadata": {
                "model": out["model"],
                "provider": provider,
                "elapsed_s": elapsed_s,
                "prompt_hash": prompt_hash,
            },
        }
    # Fallback
    fallback_json = _fallback_template(state)
    return {
        **state,
        "raw_model_output": fallback_json,
        "generation_mode": "fallback_template",
        "model_metadata": {"model": "fallback_template", "elapsed_s": elapsed_s, "prompt_hash": prompt_hash},
    }


def validate_output_schema(state: AgentState) -> AgentState:
    raw = state.get("raw_model_output", "")
    text = _strip_code_fence(raw)

    # Debug: log what the model actually returned (first 500 chars)
    mode = state.get("generation_mode", "unknown")
    logger.info("validate_output_schema: generation_mode=%s, raw_output_len=%d, first_200=%s",
                mode, len(text), text[:200])

    # Try to extract a JSON object from the text (model may wrap in prose, markdown, etc.)
    data = None
    parse_errors = []

    # Attempt 1: direct JSON parse
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        parse_errors.append(f"direct parse: {exc}")

    # Attempt 2: find the first {...} block
    if data is None:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                parse_errors.append(f"bracket extraction: {exc}")

    # Attempt 3: try fixing common JSON issues (trailing commas, single quotes)
    if data is None:
        import re
        # Remove trailing commas before } or ]
        cleaned = re.sub(r',\s*([}\]])', r'\1', text)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as exc:
                parse_errors.append(f"cleaned parse: {exc}")

    if data is None:
        logger.warning("validate_output_schema: all JSON parse attempts failed. Errors: %s", parse_errors)
        return {**state, "errors": [{"node": "validate_output_schema", "msg": f"JSON parse failed: {'; '.join(parse_errors[:3])}"}]}

    # Validate against the Pydantic schema
    try:
        draft = AdvisoryDraft.model_validate(data)
    except ValidationError as exc:
        logger.warning("validate_output_schema: Pydantic validation failed: %s", str(exc)[:500])
        return {**state, "errors": [{"node": "validate_output_schema", "msg": str(exc)[:500]}]}

    # Stale-source detection
    fresh_warnings = state.get("warnings") or []
    if state.get("crop_calendar", {}).get("is_stale"):
        fresh_warnings.append("Crop calendar source is stale (>2 years).")
        draft = draft.model_copy(update={"confidence": "low", "limitations": (draft.limitations + " Calendar source stale.").strip()})
    return {**state, "draft": draft, "warnings": fresh_warnings}


def save_draft(state: AgentState) -> AgentState:
    """Save the validated draft via the MCP `create_draft_advisory_record` tool.

    The tool logs itself to the audit trail; this node just threads the result
    into state.
    """
    if state.get("errors") or not state.get("draft"):
        return state
    draft = state["draft"]
    cc = state.get("crop_calendar") or {}
    weather = (state.get("weather") or {}).get("last_30_days") or {}

    def _observed_at(source_type: str) -> str:
        if source_type == "crop_calendar":
            return str(cc.get("season_year") or cc.get("source_date") or "")
        if source_type == "weather":
            return str(weather.get("period_end") or weather.get("as_of") or "")
        return ""

    evidence_links = [
        {
            "source_type": e.source_type,
            "source_ref": e.source_ref,
            "claim": e.claim,
            "source_url": e.source_url,
            "is_stale": e.is_stale,
            "source_observed_at": _observed_at(e.source_type),
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
    # Tool already logs to AuditEvent; we just thread state.
    if res.get("advisory_id"):
        from apps.advisories.scope import build_scope_snapshot

        meta = state.get("model_metadata") or {}
        snap = build_scope_snapshot(
            plot_history=state.get("plot_history") or [],
            warnings=state.get("warnings") or [],
        )
        Advisory.objects.filter(pk=res["advisory_id"]).update(
            scope_snapshot=snap,
            crop="maize",
            season="short_rains",
            generation_seconds=meta.get("elapsed_s"),
        )
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
    """If the model output failed Pydantic validation, switch to the fallback
    template — do NOT re-call Ollama. Re-calling a non-deterministic model
    on validation failure is wasteful and unlikely to fix structural issues.
    """
    if state.get("errors"):
        return "use_fallback_template"
    return "save_draft"


def route_after_draft(state: AgentState) -> str:
    return "validate_output_schema"


def use_fallback_template(state: AgentState) -> AgentState:
    """Replace raw_model_output with the deterministic fallback template and
    clear validation errors so save_draft can proceed.
    """
    started = time.time()
    fallback_json = _fallback_template(state)
    elapsed_s = round(time.time() - started, 2)
    new_warnings = list(state.get("warnings") or [])
    new_warnings.append("Model output failed validation; switched to deterministic fallback.")
    prior_meta = state.get("model_metadata") or {}
    return {
        **state,
        "raw_model_output": fallback_json,
        "generation_mode": "fallback_template",
        "model_metadata": {
            "model": "fallback_template",
            "prompt_hash": prior_meta.get("prompt_hash", ""),
            "elapsed_s": elapsed_s,
        },
        "errors": [],
        "warnings": new_warnings,
    }


# --- Build the graph --------------------------------------------------------

def _with_run_tracking(stage: str, fn: Callable[[AgentState], AgentState]) -> Callable[[AgentState], AgentState]:
    """Record plain-language progress on AdvisoryRun when advisory_run_id is set."""

    def wrapped(state: AgentState) -> AgentState:
        from apps.agents.models import AdvisoryRun
        from apps.agents.run_tracking import mark_run_stage

        rid = state.get("advisory_run_id")
        status = AdvisoryRun.Status.RUNNING
        if stage == "draft_advisory":
            status = AdvisoryRun.Status.WAITING_FOR_MODEL
        elif stage in {"validate_output_schema", "use_fallback_template"}:
            status = AdvisoryRun.Status.VALIDATING
        mark_run_stage(run_db_id=rid, stage=stage, status=status)
        return fn(state)

    return wrapped


def build_graph():  # type: ignore[no-untyped-def]
    g = StateGraph(AgentState)  # type: ignore[arg-type]
    g.add_node("validate_request", _with_run_tracking("validate_request", validate_request))
    g.add_node("fetch_plot_history", _with_run_tracking("fetch_plot_history", fetch_plot_history))
    g.add_node("fetch_crop_calendar", _with_run_tracking("fetch_crop_calendar", fetch_crop_calendar))
    g.add_node(
        "load_calendar_from_borrowed_mcp",
        _with_run_tracking("load_calendar_from_borrowed_mcp", load_calendar_from_borrowed_mcp),
    )
    g.add_node("fetch_weather", _with_run_tracking("fetch_weather", fetch_weather))
    g.add_node("fetch_pest_alerts", _with_run_tracking("fetch_pest_alerts", fetch_pest_alerts))
    g.add_node("fetch_market_prices", _with_run_tracking("fetch_market_prices", fetch_market_prices))
    g.add_node("validate_evidence", _with_run_tracking("validate_evidence", validate_evidence))
    g.add_node("draft_advisory", _with_run_tracking("draft_advisory", draft_advisory))
    g.add_node("validate_output_schema", _with_run_tracking("validate_output_schema", validate_output_schema))
    g.add_node("use_fallback_template", _with_run_tracking("use_fallback_template", use_fallback_template))
    g.add_node("save_draft", _with_run_tracking("save_draft", save_draft))
    g.add_node("officer_approval_gate", _with_run_tracking("officer_approval_gate", officer_approval_gate))

    g.add_edge(START, "validate_request")
    g.add_conditional_edges("validate_request", route_after_validate, {
        "officer_approval_gate": "officer_approval_gate",
        "fetch_plot_history": "fetch_plot_history",
    })
    g.add_edge("fetch_plot_history", "fetch_crop_calendar")
    g.add_edge("fetch_crop_calendar", "load_calendar_from_borrowed_mcp")
    g.add_edge("load_calendar_from_borrowed_mcp", "fetch_weather")
    g.add_edge("fetch_weather", "fetch_pest_alerts")
    g.add_edge("fetch_pest_alerts", "fetch_market_prices")
    g.add_edge("fetch_market_prices", "validate_evidence")
    g.add_edge("validate_evidence", "draft_advisory")
    g.add_conditional_edges("draft_advisory", route_after_draft, {
        "validate_output_schema": "validate_output_schema",
    })
    g.add_conditional_edges("validate_output_schema", route_after_validate_output, {
        "use_fallback_template": "use_fallback_template",
        "save_draft": "save_draft",
    })
    # After fallback, re-validate the template output (which is guaranteed JSON).
    g.add_edge("use_fallback_template", "validate_output_schema")
    g.add_conditional_edges("save_draft", route_after_save, {
        "officer_approval_gate": "officer_approval_gate",
    })
    g.add_edge("officer_approval_gate", END)

    return g.compile()
