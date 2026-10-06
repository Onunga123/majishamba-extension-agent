"""Service-layer helpers for tasks — enforces the approval gate."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.advisories.models import Advisory
from apps.approvals.models import OfficerApproval
from apps.audit.service import log_audit_event

from .models import FollowUpTask

logger = logging.getLogger("majishamba.tasks")


def _parse_deadline(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"Invalid deadline {value!r}; expected YYYY-MM-DD.") from exc


@transaction.atomic
def create_follow_up_task_after_approval(
    *,
    approved_advisory_id: int,
    officer_id: int,
    task_type: str,
    deadline: str | dt.date | None = None,
    ward: str = "Kachieng",
    actor=None,
) -> dict[str, Any]:
    """Create a follow-up task ONLY if a valid APPROVED OfficerApproval exists.

    This is the function the MCP `create_follow_up_task_after_approval` tool calls.
    It is approval-gated by design and returns an error dict if the gate is not satisfied.
    """
    try:
        advisory = Advisory.objects.get(pk=approved_advisory_id)
    except Advisory.DoesNotExist:
        return {"error": "Advisory not found", "advisory_id": approved_advisory_id}

    approval = (
        OfficerApproval.objects.filter(
            advisory_id=advisory.id,
            officer_id=officer_id,
            decision=OfficerApproval.Decision.APPROVED,
        )
        .order_by("-created_at")
        .first()
    )
    if not approval:
        logger.warning("Approval gate blocked task creation for advisory=%s by officer=%s", advisory.id, officer_id)
        return {
            "error": "Approval gate: no APPROVED OfficerApproval record for this advisory/officer.",
            "advisory_id": advisory.id,
        }

    if advisory.status != Advisory.Status.APPROVED:
        return {
            "error": f"Advisory status is {advisory.status}, not APPROVED.",
            "advisory_id": advisory.id,
        }

    if isinstance(deadline, str):
        try:
            deadline_date = _parse_deadline(deadline)
        except ValidationError as exc:
            return {"error": str(exc), "advisory_id": advisory.id}
    else:
        deadline_date = deadline

    try:
        task = FollowUpTask.objects.create(
            approved_advisory=advisory,
            owner_id=officer_id,
            task_type=task_type,
            deadline=deadline_date,
            ward=ward,
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to create task for advisory=%s", advisory.id)
        return {"error": f"Task creation failed: {exc}", "advisory_id": advisory.id}

    log_audit_event(
        actor=actor,
        action="create_follow_up_task",
        target=task,
        metadata={"advisory_id": advisory.id, "task_type": task_type, "ward": ward},
    )
    return {"task_id": task.id, "status": task.status, "advisory_id": advisory.id}
