"""Approval views."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import View

from apps.accounts.permissions import require_approver
from apps.advisories.context_helpers import advisory_review_context
from apps.advisories.models import Advisory
from apps.audit.service import log_audit_event
from apps.tasks.service import create_follow_up_task_after_approval

from .forms import OfficerApprovalForm
from .models import OfficerApproval


class ApprovalGateView(LoginRequiredMixin, View):
    """Officer reviews a DRAFT advisory and chooses an action."""

    def get(self, request: HttpRequest, advisory_pk: int) -> HttpResponse:
        require_approver(request.user)
        advisory = get_object_or_404(Advisory.objects.select_related("cluster").prefetch_related("evidence"), pk=advisory_pk)
        if advisory.status != Advisory.Status.DRAFT:
            messages.warning(request, "This advisory is no longer in DRAFT status.")
            return redirect("advisories:detail", pk=advisory.pk)
        form = OfficerApprovalForm()
        ctx = {"advisory": advisory, "form": form}
        ctx.update(advisory_review_context(advisory))
        return render(request, "approvals/gate.html", ctx)

    @transaction.atomic
    def post(self, request: HttpRequest, advisory_pk: int) -> HttpResponse | HttpResponseRedirect:
        require_approver(request.user)
        advisory = get_object_or_404(Advisory.objects.select_related("cluster"), pk=advisory_pk)
        if advisory.status != Advisory.Status.DRAFT:
            messages.error(request, "This advisory is no longer in DRAFT status — refresh and review the current version.")
            return redirect("advisories:detail", pk=advisory.pk)

        try:
            posted_version = int(request.POST.get("content_version", "0"))
        except ValueError:
            posted_version = 0
        if posted_version != advisory.content_version:
            messages.error(
                request,
                "This advisory was updated while you were reviewing. Please read the latest version before deciding.",
            )
            return redirect("advisories:detail", pk=advisory.pk)

        form = OfficerApprovalForm(request.POST)
        if not form.is_valid():
            ctx = {"advisory": advisory, "form": form}
            ctx.update(advisory_review_context(advisory))
            return render(request, "approvals/gate.html", ctx)

        locked = Advisory.objects.select_for_update().get(pk=advisory.pk)
        if locked.content_version != posted_version or locked.status != Advisory.Status.DRAFT:
            messages.error(request, "Advisory changed during submission. Please review again.")
            return redirect("advisories:detail", pk=advisory.pk)

        approval = form.save(commit=False)
        approval.advisory = locked
        approval.officer = request.user
        approval.save()

        if approval.decision == OfficerApproval.Decision.APPROVED:
            locked.status = Advisory.Status.APPROVED
        elif approval.decision == OfficerApproval.Decision.REJECTED:
            locked.status = Advisory.Status.REJECTED
        elif approval.decision == OfficerApproval.Decision.DEFERRED:
            locked.status = Advisory.Status.DEFERRED
        else:
            locked.status = Advisory.Status.NEEDS_EVIDENCE
        locked.save(update_fields=["status", "updated_at"])

        log_audit_event(
            actor=request.user,
            action="officer_approval",
            target=locked,
            metadata={
                "decision": approval.decision,
                "comments": approval.comments[:200],
                "content_version": locked.content_version,
            },
        )

        if approval.decision == OfficerApproval.Decision.APPROVED and request.POST.get("create_followup"):
            task_type = request.POST.get("task_type", "field_visit")
            deadline = request.POST.get("deadline")
            res = create_follow_up_task_after_approval(
                approved_advisory_id=locked.id,
                officer_id=request.user.id,
                task_type=task_type,
                deadline=deadline,
                ward=locked.ward,
                actor=request.user,
            )
            if res.get("task_id"):
                messages.success(request, f"Follow-up task #{res['task_id']} created (internal — no message sent to farmers).")
            else:
                messages.error(request, f"Could not create task: {res.get('error')}")

        messages.success(request, f"Advisory marked {locked.get_status_display()}. No farmer message was sent.")
        return redirect("advisories:detail", pk=locked.pk)
