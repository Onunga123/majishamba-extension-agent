"""Advisory models — DRAFT → APPROVED/REJECTED lifecycle with soft-delete."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.clusters.models import FarmerCluster


class ActiveAdvisoryManager(models.Manager):
    """Default manager — excludes soft-deleted advisories."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class AllAdvisoryManager(models.Manager):
    """Includes soft-deleted advisories. Used by the 'Deleted advisories' view
    and by audit/compliance queries. Never exposed to viewers."""

    def get_queryset(self):
        return super().get_queryset().all()


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
    content_version = models.PositiveIntegerField(
        default=1,
        help_text="Incremented when a DRAFT is edited; approval must match this version.",
    )
    scope_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Household/plot scope captured when this advisory was drafted (not live DB counts).",
    )
    crop = models.CharField(max_length=40, default="maize")
    season = models.CharField(max_length=40, default="short_rains")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advisories_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Soft-delete support ---
    deleted_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Set when an advisory is soft-deleted. NULL = active.",
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="advisories_deleted",
        help_text="Officer who soft-deleted this advisory.",
    )
    deletion_reason = models.CharField(
        max_length=200, blank=True,
        help_text="Reason for soft-deletion (internal officer note).",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "cluster"]),
            models.Index(fields=["deleted_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Advisory {self.id} — {self.cluster.cluster_id} {self.get_status_display()}"

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self, *, by_user, reason: str = "") -> None:
        """Soft-delete this advisory. Preserves the record for audit."""
        from django.utils import timezone
        self.deleted_at = timezone.now()
        self.deleted_by = by_user
        self.deletion_reason = reason
        self.save(update_fields=["deleted_at", "deleted_by", "deletion_reason", "updated_at"])

    def restore(self) -> None:
        """Restore a soft-deleted advisory."""
        self.deleted_at = None
        self.deleted_by = None
        self.deletion_reason = ""
        self.save(update_fields=["deleted_at", "deleted_by", "deletion_reason", "updated_at"])

    # Managers: `objects` excludes soft-deleted; `all_objects` includes everything.
    objects = ActiveAdvisoryManager()
    all_objects = AllAdvisoryManager()


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
    source_observed_at = models.CharField(
        max_length=40,
        blank=True,
        help_text="Source observation or publication date — not the same as retrieval time.",
    )
    source_url = models.URLField(blank=True)

    class Meta:
        ordering = ("id",)
