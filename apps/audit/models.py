"""Audit event log — immutable record of all key actions."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Every key action (tool call, approval, task creation) produces one row."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=80, blank=True)
    metadata = models.JSONField(default=dict)
    tool_name = models.CharField(max_length=80, blank=True)
    inputs_summary = models.JSONField(default=dict, blank=True)
    outputs_summary = models.JSONField(default=dict, blank=True)
    approval_status = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["tool_name", "created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M:%S}"
