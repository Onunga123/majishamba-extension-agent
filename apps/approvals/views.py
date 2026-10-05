"""Approval views."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import View

from apps.accounts.permissions import require_approver
from apps.advisories.models import Advisory
from apps.audit.service import log_audit_event
from apps.tasks.service import create_follow_up_task_after_approval

from .forms import OfficerApprovalForm
from .models import OfficerApproval


class ApprovalGateView(LoginRequiredMixin, View):
    """Officer reviews a DRAFT advisory and chooses an action."""

    def get(self, request: HttpRequest, advisory_pk: int) -> HttpResponse:
        require_approver(request.user)
        advisory = get_object_or_404(Advisory, pk=advisory_pk)
        form = OfficerApprovalForm()
        return render(
            request,
            "approvals/gate.html",
            {"advisory": advisory, "form": form},
        )

    def post(self, request: HttpRequest, advisory_pk: int) -> HttpResponse | HttpResponseRedirect:
        require_approver(request.user)
        advisory = get_object_or_404(Advisory, pk=advisory_pk)
        form = OfficerApprovalForm(request.POST)
        if not form.is_valid():
            return render(request, "approvals/gate.html", {"advisory": advisory, "form": form})

        approval = form.save(commit=False)
        approval.advisory = advisory
        approval.officer = request.user
        approval.save()

        # Reflect decision on the advisory record
        if approval.decision == OfficerApproval.Decision.APPROVED:
            advisory.status = Advisory.Status.APPROVED
        elif approval.decision == OfficerApproval.Decision.REJECTED:
            advisory.status = Advisory.Status.REJECTED
        elif approval.decision == OfficerApproval.Decision.DEFERRED:
            advisory.status = Advisory.Status.DEFERRED
        else:
            advisory.status = Advisory.Status.NEEDS_EVIDENCE
        advisory.save(update_fields=["status", "updated_at"])

        log_audit_event(
            actor=request.user,
            action="officer_approval",
            target=advisory,
            metadata={"decision": approval.decision, "comments": approval.comments[:200]},
        )

        # If approved AND the officer requested a follow-up task, create it.
        if approval.decision == OfficerApproval.Decision.APPROVED and request.POST.get("create_followup"):
            task_type = request.POST.get("task_type", "field_visit")
            deadline = request.POST.get("deadline")
            res = create_follow_up_task_after_approval(
                approved_advisory_id=advisory.id,
                officer_id=request.user.id,
                task_type=task_type,
                deadline=deadline,
                ward=advisory.ward,
                actor=request.user,
            )
            if res.get("task_id"):
                messages.success(request, f"Follow-up task #{res['task_id']} created.")
            else:
                messages.error(request, f"Could not create task: {res.get('error')}")

        messages.success(request, f"Advisory marked {advisory.get_status_display()}.")
        return redirect("advisories:detail", pk=advisory.pk)
