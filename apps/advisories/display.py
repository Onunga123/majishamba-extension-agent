"""Officer-facing labels for advisories (no misleading model claims)."""
from __future__ import annotations

from .models import Advisory


def generation_mode_label(advisory: Advisory) -> str:
    mode = advisory.generation_mode or ""
    if mode == "fallback_template":
        return "Template-generated draft — model unavailable"
    if mode == "ollama_qwen" and advisory.model_name:
        return f"Model-generated draft — {advisory.model_name}"
    if mode == "ollama_qwen":
        return "Model-generated draft — open-weights model (see metadata)"
    return "Draft generation mode not recorded"


def confidence_explanation(confidence: str) -> str:
    mapping = {
        "low": "Sources conflict, are stale, or key plot records are missing — verify locally before acting.",
        "medium": "Evidence is usable but the officer should confirm local conditions.",
        "high": "Evidence is complete and fresh enough for review — officer still decides.",
    }
    return mapping.get(confidence, "Officer judgment required — confidence is a review aid only.")
