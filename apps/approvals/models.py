"""Officer approval records — the human gate before any task is created."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.advisories.models import Advisory


class OfficerApproval(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        DEFERRED = "deferred", "Deferred"
        NEEDS_EVIDENCE = "needs_evidence", "Needs more evidence"

    advisory = models.ForeignKey(Advisory, on_delete=models.PROTECT, related_name="approvals")
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="approvals_given",
    )
    decision = models.CharField(max_length=40, choices=Decision.choices)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.officer} {self.get_decision_display()} Advisory {self.advisory_id}"
