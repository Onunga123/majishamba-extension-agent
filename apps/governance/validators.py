"""Content validators for ingested weather, pest, and advisory data.

These validators catch data-quality issues BEFORE a record enters production
evidence. They do NOT verify authenticity — only structural quality and
internal consistency.

Key principles:
- Reject meaningless placeholder text ("eee", "test", single characters)
- Require onset_status to be supported by explicit language in the forecast text
- Require minimum content length for forecast summaries
- Flag zero-validity-window forecasts as suspicious
- Send failed records to a review queue (verification_status="review_required")
- Never silently delete or modify existing records
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# --- Constants ---
MIN_FORECAST_SUMMARY_LENGTH = 20  # characters — "eee" is 3 chars, fails
PLACEHOLDER_PATTERNS = [
    r"^(eee+|test+|xxx+|aaa+|fff+|asdf|qwerty|123+|abc+|lorem\s+ipsum)$",
    r"^(n/?a|none|tbd|todo|placeholder)$",
    r"^\s+$",  # whitespace only
]

ONSET_KEYWORDS = {
    "onset_confirmed": ["onset", "rain has started", "rains have started", "season has started", "planting can begin"],
    "onset_delayed": ["onset delay", "delayed onset", "late onset", "onset is delayed"],
    "false_start": ["false start", "false onset", "premature rain", "rain stopped"],
}
ONSET_UNKNOWN = "unknown"


@dataclass
class ValidationResult:
    """Result of content validation. Describes what passed and what failed."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggested_verification_status: str = "current_official"  # or "review_required"


def validate_weather_content(
    *,
    forecast_summary: str,
    onset_status: str,
    rainfall_mm: float | None,
    rainfall_period_note: str,
    valid_from: Any = None,
    valid_to: Any = None,
    publication_date: Any = None,
) -> ValidationResult:
    """Validate a weather bulletin's content before accepting it as production evidence.

    Returns a ValidationResult with:
    - is_valid: True if the record passes all checks
    - errors: list of blocking errors (record should be quarantined)
    - warnings: list of non-blocking warnings (record accepted but flagged)
    - suggested_verification_status: "current_official" or "review_required"
    """
    result = ValidationResult(is_valid=True)

    # --- Check 1: forecast_summary is not empty or placeholder ---
    summary = (forecast_summary or "").strip()
    if len(summary) < MIN_FORECAST_SUMMARY_LENGTH:
        result.errors.append(
            f"forecast_summary is too short ({len(summary)} chars; minimum {MIN_FORECAST_SUMMARY_LENGTH}). "
            f"Meaningless placeholder text like 'eee' is not acceptable as official content."
        )
        result.is_valid = False

    for pattern in PLACEHOLDER_PATTERNS:
        if re.match(pattern, summary, re.IGNORECASE):
            result.errors.append(
                f"forecast_summary appears to be placeholder text ({summary!r}). "
                f"Accept only substantive content transcribed from the official bulletin."
            )
            result.is_valid = False
            break

    # --- Check 2: onset_status is supported by forecast text ---
    if onset_status in ONSET_KEYWORDS:
        keywords = ONSET_KEYWORDS[onset_status]
        summary_lower = summary.lower()
        if not any(kw in summary_lower for kw in keywords):
            result.errors.append(
                f"onset_status={onset_status!r} is not supported by the forecast text. "
                f"The summary must contain one of: {keywords}. "
                f"If the bulletin does not explicitly report onset, use onset_status='unknown'."
            )
            result.is_valid = False

    # If onset_status is "unknown" but the text mentions onset keywords, warn
    if onset_status == ONSET_UNKNOWN and summary:
        summary_lower = summary.lower()
        for status, keywords in ONSET_KEYWORDS.items():
            if any(kw in summary_lower for kw in keywords):
                result.warnings.append(
                    f"forecast text mentions onset-related language ({keywords}) "
                    f"but onset_status is 'unknown'. Consider reviewing the bulletin."
                )
                break

    # --- Check 3: rainfall with note (already enforced by the adapter, but double-check) ---
    if rainfall_mm is not None and not rainfall_period_note:
        result.errors.append(
            "rainfall_mm is set but rainfall_period_note is empty. "
            "Numeric rainfall must record the period and geographic scope it applies to."
        )
        result.is_valid = False

    # --- Check 4: zero validity window ---
    if valid_from and valid_to and publication_date:
        if str(valid_from) == str(valid_to) == str(publication_date):
            result.warnings.append(
                "valid_from, valid_to, and publication_date are all the same date. "
                "A daily forecast with a zero-day validity window is unusual — "
                "verify the dates are correct."
            )

    # --- Set suggested verification status ---
    if not result.is_valid:
        result.suggested_verification_status = "review_required"
    elif result.warnings:
        result.suggested_verification_status = "current_official"  # accepted with warnings

    return result


def validate_pest_content(
    *,
    pest: str,
    crop: str,
    severity: str,
    advisory: str,
    coverage_level: str,
) -> ValidationResult:
    """Validate a pest notice's content before accepting it."""
    result = ValidationResult(is_valid=True)

    if len((pest or "").strip()) < 3:
        result.errors.append("pest name is too short — must be a real pest name (e.g. 'Fall Armyworm').")
        result.is_valid = False

    if len((crop or "").strip()) < 2:
        result.errors.append("crop name is too short.")
        result.is_valid = False

    # Severity must be a valid choice, not inflated
    valid_severities = {"not_specified", "low", "moderate", "high", "extreme"}
    if severity not in valid_severities:
        result.errors.append(f"severity={severity!r} is not a valid choice. Use one of: {valid_severities}.")
        result.is_valid = False

    # If severity is high/extreme, the advisory text should mention the severity
    if severity in {"high", "extreme"} and advisory:
        severity_words = severity.lower()
        if severity_words not in advisory.lower() and "severe" not in advisory.lower():
            result.warnings.append(
                f"severity={severity!r} but advisory text does not mention '{severity}' or 'severe'. "
                f"Ensure the severity is stated in the source."
            )

    if not result.is_valid:
        result.suggested_verification_status = "review_required"

    return result


def is_meaningful_text(text: str, min_length: int = 20) -> bool:
    """Check if a text string contains meaningful content (not placeholder)."""
    if not text or len(text.strip()) < min_length:
        return False
    for pattern in PLACEHOLDER_PATTERNS:
        if re.match(pattern, text.strip(), re.IGNORECASE):
            return False
    return True
