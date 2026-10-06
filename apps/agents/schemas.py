"""Pydantic schemas for advisory draft, evidence, and tool I/O.

These schemas are used both by the LangGraph nodes (validation) and the
custom MCP server (input/output validation). Keeping them in one place
guarantees the agent and the MCP tools agree on shape.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# --- Tool input schemas ---------------------------------------------------

class GetClusterPlotHistoryInput(BaseModel):
    cluster_id: str = Field(..., examples=["KACH-01"])
    ward: str = Field("Kachieng")
    sub_county: str = Field("Nyatike")
    county: str = Field("Migori")


class GetCropCalendarInput(BaseModel):
    crop: Literal["maize"] = "maize"
    zone: str = Field("Migori-Low-Mid")
    season: Literal["short_rains", "long_rains"] = "short_rains"


class GetWeatherAndRainfallContextInput(BaseModel):
    sub_county: str = Field("Nyatike")
    period: Literal["last_30_days", "10_day_forecast"] = "last_30_days"


class GetPestAlertsInput(BaseModel):
    crop: Literal["maize"] = "maize"
    county: str = Field("Migori")
    region: str = Field("Nyanza")


class GetMarketPriceContextInput(BaseModel):
    crop: Literal["maize"] = "maize"
    market: str = Field("Migori-Town")


class ValidateAdvisoryEvidenceInput(BaseModel):
    advisory_draft: str
    evidence: list[dict]


class CreateDraftAdvisoryRecordInput(BaseModel):
    advisory_text: str
    evidence_links: list[dict]
    model_metadata: dict
    cluster_id: str
    ward: str = "Kachieng"
    sub_county: str = "Nyatike"
    county: str = "Migori"


class CreateFollowUpTaskAfterApprovalInput(BaseModel):
    approved_advisory_id: int
    officer_id: int
    task_type: str
    deadline: str | None = None
    ward: str = "Kachieng"


# --- Advisory draft schema -------------------------------------------------

class EvidenceLink(BaseModel):
    source_type: str
    source_ref: str
    claim: str
    is_stale: bool = False
    source_url: str = ""


class AdvisoryDraft(BaseModel):
    """Strict schema the agent must emit before saving as DRAFT."""

    recommendation_type: Literal[
        "plant",
        "delay",
        "verify_locally",
        "pest_monitoring",
        "data_gap",
    ]
    summary: str = Field(..., max_length=240)
    body: str
    confidence: Literal["low", "medium", "high"] = "medium"
    limitations: str = ""
    evidence: list[EvidenceLink] = Field(default_factory=list)

    @field_validator("body")
    @classmethod
    def body_must_be_substantive(cls, v: str) -> str:
        if len(v.strip()) < 80:
            raise ValueError("Advisory body is too short — must be substantive.")
        return v.strip()

    @field_validator("evidence")
    @classmethod
    def evidence_must_be_cited(cls, v: list[EvidenceLink]) -> list[EvidenceLink]:
        if not v:
            raise ValueError("Advisory must cite at least one evidence source.")
        return v
