"""Domain service for recording an officer's approval decision on a DRAFT advisory.

Extracted from ``apps.approvals.views.ApprovalGateView`` so the web form and
the public API share one transactional implementation: optimistic version
check, pessimistic ``select_for_update`` lock, approval row creation,
advisory status advance, audit log, and optional follow-up task.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from apps.accounts.permissions import require_approver_or_admin
from apps.advisories.models import Advisory
from apps.audit.service import log_audit_event
from apps.tasks.service import create_follow_up_task_after_approval

from .models import OfficerApproval


class ApprovalError(Exception):
    """Base class for approval service errors."""


class AdvisoryNotFound(ApprovalError):
    """No Advisory matches the supplied pk."""


class AdvisoryNotDraft(ApprovalError):
    """The advisory is not in DRAFT status and cannot be approved."""


class VersionMismatch(ApprovalError):
    """The advisory's content_version changed between review and submission."""


_DECISION_TO_STATUS = {
    OfficerApproval.Decision.APPROVED: Advisory.Status.APPROVED,
    OfficerApproval.Decision.REJECTED: Advisory.Status.REJECTED,
    OfficerApproval.Decision.DEFERRED: Advisory.Status.DEFERRED,
    OfficerApproval.Decision.NEEDS_EVIDENCE: Advisory.Status.NEEDS_EVIDENCE,
}


@dataclass(frozen=True)
class ApprovalResult:
    advisory_id: int
    status: str
    approval_id: int
    followup_task_id: int | None = None
    followup_error: str | None = None


@transaction.atomic
def record_approval(
    *,
    actor,
    advisory_pk: int,
    decision: str,
    comments: str = "",
    content_version: int,
    create_followup: bool = False,
    task_type: str = "field_visit",
    deadline: str | None = None,
) -> ApprovalResult:
    """Persist an officer approval and advance the advisory's status.

    Raises ``AdvisoryNotFound``, ``AdvisoryNotDraft``, or ``VersionMismatch``.
    """
    require_approver_or_admin(actor)
    try:
        advisory = Advisory.objects.select_related("cluster").get(pk=advisory_pk)
    except Advisory.DoesNotExist as exc:
        raise AdvisoryNotFound(f"Advisory {advisory_pk} not found.") from exc

    if advisory.status != Advisory.Status.DRAFT:
        raise AdvisoryNotDraft("Only DRAFT advisories can be approved.")
    if content_version != advisory.content_version:
        raise VersionMismatch("Advisory content_version does not match the reviewed version.")

    # Pessimistic lock: re-check under the row lock so two concurrent
    # approvals cannot both succeed against the same version.
    locked = Advisory.objects.select_for_update().get(pk=advisory.pk)
    if locked.content_version != content_version or locked.status != Advisory.Status.DRAFT:
        raise VersionMismatch("Advisory changed during submission.")

    approval = OfficerApproval.objects.create(
        advisory=locked,
        officer=actor,
        decision=decision,
        comments=comments,
    )
    locked.status = _DECISION_TO_STATUS.get(decision, Advisory.Status.NEEDS_EVIDENCE)
    locked.save(update_fields=["status", "updated_at"])

    log_audit_event(
        actor=actor,
        action="officer_approval",
        target=locked,
        metadata={
            "decision": approval.decision,
            "comments": approval.comments[:200],
            "content_version": locked.content_version,
        },
    )

    followup_task_id = None
    followup_error = None
    if decision == OfficerApproval.Decision.APPROVED and create_followup:
        res = create_follow_up_task_after_approval(
            approved_advisory_id=locked.id,
            officer_id=actor.id,
            task_type=task_type,
            deadline=deadline,
            ward=locked.ward,
            actor=actor,
        )
        followup_task_id = res.get("task_id")
        if not followup_task_id:
            followup_error = res.get("error", "Could not create follow-up task.")

    return ApprovalResult(
        advisory_id=locked.id,
        status=locked.status,
        approval_id=approval.id,
        followup_task_id=followup_task_id,
        followup_error=followup_error,
    )
