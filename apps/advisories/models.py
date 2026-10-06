"""Advisory models — DRAFT → APPROVED/REJECTED lifecycle."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.clusters.models import FarmerCluster


class Advisory(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        DEFERRED = "deferred", "Deferred"
        NEEDS_EVIDENCE = "needs_evidence", "Needs more evidence"

    class Recommendation(models.TextChoices):
        PLANT = "plant", "Planting window suitable"
        DELAY = "delay", "Delay planting, verify local onset"
        VERIFY_LOCALLY = "verify_locally", "Verify locally"
        PEST_MONITORING = "pest_monitoring", "Pest monitoring"
        DATA_GAP = "data_gap", "Data gap — officer follow-up"

    cluster = models.ForeignKey(FarmerCluster, on_delete=models.PROTECT, related_name="advisories")
    recommendation_type = models.CharField(max_length=40, choices=Recommendation.choices)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.DRAFT)

    summary = models.CharField(max_length=240)
    body = models.TextField(help_text="Structured advisory text with sources.")
    confidence = models.CharField(max_length=20, default="medium")
    limitations = models.TextField(blank=True)

    county = models.CharField(max_length=80, default="Migori")
    sub_county = models.CharField(max_length=80, default="Nyatike")
    ward = models.CharField(max_length=80, default="Kachieng")

    # Open-weights model metadata (Qwen2.5-7B-Instruct via Ollama) or "fallback_template"
    model_name = models.CharField(max_length=120, blank=True)
    model_run_id = models.CharField(max_length=120, blank=True)
    model_prompt_hash = models.CharField(max_length=64, blank=True)
    generation_seconds = models.FloatField(
        null=True, blank=True,
        help_text="Wall-clock seconds spent in the draft_advisory node (model call or fallback).",
    )
    generation_mode = models.CharField(
        max_length=40,
        default="fallback_template",
        help_text="One of: 'ollama_qwen', 'fallback_template'.",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advisories_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["status", "cluster"])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Advisory {self.id} — {self.cluster.cluster_id} {self.get_status_display()}"


class AdvisoryEvidence(models.Model):
    """Links an advisory to a specific source record + the claim it supports."""

    advisory = models.ForeignKey(Advisory, on_delete=models.CASCADE, related_name="evidence")
    source_type = models.CharField(
        max_length=40,
        help_text="One of: 'plot_history', 'crop_calendar', 'weather', 'pest', 'market', 'other'.",
    )
    source_ref = models.CharField(
        max_length=160,
        help_text="Human-readable reference to the source record (e.g. 'WeatherSignal#12').",
    )
    claim = models.TextField(help_text="What this evidence supports in the advisory.")
    is_stale = models.BooleanField(default=False)
    retrieved_at = models.DateTimeField(null=True, blank=True)
    source_url = models.URLField(blank=True)

    class Meta:
        ordering = ("id",)
