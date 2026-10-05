"""LangGraph state for MajiShamba Extension Agent."""
from __future__ import annotations

from typing import TypedDict

from .schemas import AdvisoryDraft


class AgentState(TypedDict, total=False):
    """State passed through the LangGraph workflow."""

    # Inputs
    cluster_id: str
    ward: str
    sub_county: str
    county: str
    actor_id: int | None
    request_id: str

    # Tool outputs
    plot_history: list[dict]
    crop_calendar: dict
    weather: dict
    pest_alerts: list[dict]
    market_prices: list[dict]
    evidence_validation: dict

    # Drafting
    draft: AdvisoryDraft | None
    raw_model_output: str
    generation_mode: str  # 'ollama_qwen' | 'fallback_template'
    model_metadata: dict

    # Errors
    errors: list[dict]
    warnings: list[str]

    # Output
    advisory_id: int | None
