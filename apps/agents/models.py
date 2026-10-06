"""Agent run tracking for officer-visible progress."""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from apps.clusters.models import FarmerCluster


class AdvisoryRun(models.Model):
    """One officer-initiated advisory generation run."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        WAITING_FOR_MODEL = "waiting_for_model", "Waiting for model"
        VALIDATING = "validating", "Validating"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_FALLBACK = "completed_with_fallback", "Completed with template fallback"
        FAILED = "failed", "Failed"

    run_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="advisory_runs",
    )
    cluster = models.ForeignKey(FarmerCluster, on_delete=models.PROTECT, related_name="advisory_runs")
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.QUEUED)
    current_stage = models.CharField(max_length=80, blank=True)
    current_message = models.CharField(max_length=240, blank=True)
    completed_stages = models.JSONField(default=list, blank=True)
    result_advisory = models.ForeignKey(
        "advisories.Advisory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_runs",
    )
    error_message = models.CharField(max_length=500, blank=True)
    generation_mode = models.CharField(max_length=40, blank=True)
    pipeline_request_id = models.CharField(max_length=64, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["requested_by", "status", "created_at"]),
            models.Index(fields=["cluster", "status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Run {self.run_id} — {self.cluster.cluster_id} ({self.status})"
