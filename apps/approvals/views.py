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

from .forms import OfficerApprovalForm


class ApprovalGateView(LoginRequiredMixin, View):
    """Officer reviews a DRAFT advisory and chooses an action."""

    def get(self, request: HttpRequest, advisory_pk: int) -> HttpResponse:
        require_approver(request.user)
        advisory = get_object_or_404(
            Advisory.objects.select_related("cluster").prefetch_related("evidence"), pk=advisory_pk
        )
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
            messages.error(
                request,
                "This advisory is no longer in DRAFT status — refresh and review the current version.",
            )
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

        from apps.approvals.services import (
            AdvisoryNotDraft,
            VersionMismatch,
            record_approval,
        )

        try:
            result = record_approval(
                actor=request.user,
                advisory_pk=advisory.pk,
                decision=form.cleaned_data["decision"],
                comments=form.cleaned_data.get("comments", "") or "",
                content_version=posted_version,
                create_followup=bool(request.POST.get("create_followup")),
                task_type=request.POST.get("task_type", "field_visit"),
                deadline=request.POST.get("deadline"),
            )
        except AdvisoryNotDraft:
            messages.error(
                request,
                "This advisory is no longer in DRAFT status — refresh and review the current version.",
            )
            return redirect("advisories:detail", pk=advisory.pk)
        except VersionMismatch:
            messages.error(request, "Advisory changed during submission. Please review again.")
            return redirect("advisories:detail", pk=advisory.pk)

        if result.followup_task_id:
            messages.success(
                request,
                f"Follow-up task #{result.followup_task_id} created (internal — no message sent to farmers).",
            )
        elif result.followup_error:
            messages.error(request, f"Could not create task: {result.followup_error}")

        status_display = Advisory.Status(result.status).label
        messages.success(request, f"Advisory marked {status_display}. No farmer message was sent.")
        return redirect("advisories:detail", pk=result.advisory_id)
