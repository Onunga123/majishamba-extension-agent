"""Presentational template filters for advisory evidence rows.

These filters parse the dense `claim` strings that the advisory pipeline
writes into AdvisoryEvidence.claim for weather evidence rows. They are
strictly presentational — they do NOT query the database, do NOT change
the underlying value, and do NOT manufacture data. If the claim string
does not match the expected weather-evidence shape, the filters return
empty strings so the template falls back to showing the raw claim text.
"""
from __future__ import annotations

import re

from django import template

register = template.Library()


# Pattern matches strings like:
#   "last30: 120.0mm onset=unknown; forecast: moderate rainfall expected by day 4–6"
# Captures:
#   1. rainfall amount (e.g. "120.0mm")
#   2. onset status (e.g. "unknown")
#   3. forecast text (e.g. "moderate rainfall expected by day 4–6")
_WEATHER_CLAIM_RE = re.compile(
    r"last30:\s*(?P<rainfall>[^;\n]+?)\s+onset=(?P<onset>[^;\n]+?);?\s*forecast:\s*(?P<forecast>.+)",
    re.IGNORECASE | re.DOTALL,
)


@register.filter
def is_weather_claim(claim: str) -> bool:
    """Return True if the claim string matches the weather-evidence
    shape (last30: ... onset=... ; forecast: ...)."""
    if not claim:
        return False
    return bool(_WEATHER_CLAIM_RE.search(claim))


@register.filter
def weather_rainfall(claim: str) -> str:
    """Extract the rainfall amount (e.g. '120.0mm') from a weather claim."""
    if not claim:
        return ""
    m = _WEATHER_CLAIM_RE.search(claim)
    if not m:
        return ""
    return m.group("rainfall").strip()


@register.filter
def weather_onset(claim: str) -> str:
    """Extract the rainfall onset status (e.g. 'unknown') from a weather
    claim, capitalised for display."""
    if not claim:
        return ""
    m = _WEATHER_CLAIM_RE.search(claim)
    if not m:
        return ""
    onset = m.group("onset").strip()
    # Capitalise the first letter for display ("unknown" → "Unknown").
    return onset[:1].upper() + onset[1:] if onset else ""


@register.filter
def weather_forecast(claim: str) -> str:
    """Extract the forecast text from a weather claim."""
    if not claim:
        return ""
    m = _WEATHER_CLAIM_RE.search(claim)
    if not m:
        return ""
    return m.group("forecast").strip()
