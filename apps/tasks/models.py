"""Follow-up tasks — created only after officer approval."""
from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.db import models

from apps.advisories.models import Advisory


class FollowUpTask(models.Model):
    class TaskType(models.TextChoices):
        FIELD_VISIT = "field_visit", "Field visit to Kachieng cluster"
        CLUSTER_MEETING = "cluster_meeting", "Cluster meeting in Kachieng"
        RE_EVIDENCE = "re_evidence", "Re-collect evidence"
        PRINT_ADVISORY = "print_advisory", "Print advisory for delivery"

    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    approved_advisory = models.ForeignKey(
        Advisory,
        on_delete=models.PROTECT,
        related_name="follow_up_tasks",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="follow_up_tasks",
    )
    task_type = models.CharField(max_length=40, choices=TaskType.choices)
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.ASSIGNED)
    ward = models.CharField(max_length=80, default="Kachieng")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def is_overdue(self, *, as_of: dt.date | None = None) -> bool:
        if not self.deadline:
            return False
        as_of = as_of or dt.date.today()
        return self.deadline < as_of and self.status != self.Status.COMPLETED
