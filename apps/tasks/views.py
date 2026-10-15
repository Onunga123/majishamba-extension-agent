from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from apps.accounts.models import User
from apps.audit.service import log_audit_event

from .forms import FieldFindingForm, TaskStatusForm
from .models import FieldFinding, FollowUpTask


class FollowUpTaskListView(LoginRequiredMixin, ListView):
    """List follow-up tasks.

    Phase D (D-02): all authenticated users can view the task list (the
    about page documents "read-only access to ... tasks" for Viewers).
    However, per docs/governance/synthetic_data_notice.md:31,76, officer
    real names must NOT be displayed in any UI surface visible to a Viewer
    role. The template uses the ``is_viewer`` context flag to redact
    ``owner.display_name`` to a role label for Viewers. Officers,
    Supervisors, and System Administrators see the full names.
    """

    model = FollowUpTask
    template_name = "tasks/list.html"
    context_object_name = "tasks"
    paginate_by = 25

    def get_queryset(self):
        return FollowUpTask.objects.select_related("approved_advisory__cluster", "owner").order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_viewer"] = self.request.user.role == User.Role.VIEWER
        return ctx


class FollowUpTaskDetailView(LoginRequiredMixin, DetailView):
    """Show a single follow-up task and its field findings.

    Phase D (D-02): all authenticated users can view task details (the
    about page documents "read-only access to ... tasks" for Viewers).
    However, per docs/governance/synthetic_data_notice.md:31,76, officer
    real names must NOT be displayed in any UI surface visible to a Viewer
    role. The template uses the ``is_viewer`` context flag to redact
    ``owner.display_name``, ``submitted_by.display_name``, and
    ``verified_by.display_name`` to role labels for Viewers. Officers,
    Supervisors, and System Administrators see the full names.

    D-02 correction (server-side data minimization): internal field-finding
    content (observations, missing_information, follow_up_notes) is
    restricted to officers and supervisors. For Viewers, ``field_findings``
    is NOT prefetched in the queryset and the ``findings`` context variable
    is an empty list, so the findings text is never present in the Viewer
    response — neither in the rendered HTML nor in the template context.
    The ``show_findings`` context flag gates the "Submitted findings"
    section in the template. This is server-side enforcement, not
    template-only hiding: the data is absent from the response.
    """

    model = FollowUpTask
    template_name = "tasks/detail.html"
    context_object_name = "task"

    def get_queryset(self):
        is_viewer = self.request.user.role == User.Role.VIEWER
        qs = FollowUpTask.objects.select_related(
            "approved_advisory__cluster",
            "owner",
        )
        # D-02 correction: do NOT prefetch field_findings for Viewers.
        # Officers and supervisors get the prefetched relation; Viewers
        # get the task object without the findings relation loaded.
        if not is_viewer:
            qs = qs.prefetch_related("field_findings")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        is_viewer = self.request.user.role == User.Role.VIEWER
        ctx["is_viewer"] = is_viewer
        # D-02 correction: pass findings as an explicit context variable.
        # For Viewers, this is an empty list — the findings content is
        # never in the Viewer's response. For officers/supervisors, the
        # prefetched findings are passed through. The template iterates
        # this variable (not ``task.field_findings.all``) so the data
        # path is controlled server-side.
        if is_viewer:
            ctx["findings"] = []
            ctx["show_findings"] = False
        else:
            ctx["findings"] = list(self.object.field_findings.all())
            ctx["show_findings"] = True
        return ctx


class TaskFieldFindingView(LoginRequiredMixin, View):
    """Record internal field findings — does not send farmer messages.

    Phase D (D-11): findings may only be submitted when the task is in
    ASSIGNED or IN_PROGRESS. Submitting findings on COMPLETED, VERIFIED,
    CLOSED, or CANCELLED tasks is rejected with 403; no finding is
    persisted and the task status is unchanged.

    Phase D (R-1): only application officers (extension_officer/supervisor)
    may submit findings. Task ownership alone is not sufficient — a
    Viewer or System Administrator who happens to own a task (via an
    abnormal path) must not be able to submit findings.
    """

    # D-11: valid source states for finding submission.
    _VALID_FINDING_STATES = frozenset({
        FollowUpTask.Status.ASSIGNED,
        FollowUpTask.Status.IN_PROGRESS,
    })

    def post(self, request: HttpRequest, pk: int) -> HttpResponse | HttpResponseRedirect:
        task = get_object_or_404(FollowUpTask, pk=pk)
        # R-1: require is_officer() — task ownership alone is not sufficient.
        if not request.user.is_officer():
            raise PermissionDenied("Only extension officers and supervisors can submit field findings.")
        # D-11: reject findings on tasks not in ASSIGNED or IN_PROGRESS.
        if task.status not in self._VALID_FINDING_STATES:
            raise PermissionDenied(
                f"Cannot submit findings for a task in '{task.status}' status. "
                "Findings may only be submitted for assigned or in-progress tasks."
            )
        form = FieldFindingForm(request.POST)
        if not form.is_valid():
            # Re-render the detail page with the form errors. Only
            # officers/supervisors reach this path, so we pass the full
            # findings context — the same shape that
            # FollowUpTaskDetailView.get_context_data produces for
            # non-viewer users.
            return render(request, "tasks/detail.html", {
                "task": task,
                "finding_form": form,
                "is_viewer": False,
                "findings": list(task.field_findings.all()),
                "show_findings": True,
            })
        finding = form.save(commit=False)
        finding.task = task
        finding.submitted_by = request.user
        finding.checklist = {
            "onset_verified_locally": request.POST.get("onset_verified_locally") == "yes",
            "pest_scouting_done": request.POST.get("pest_scouting_done") == "yes",
        }
        finding.save()
        previous_status = task.status
        if task.status == FollowUpTask.Status.ASSIGNED:
            task.status = FollowUpTask.Status.IN_PROGRESS
            task.save(update_fields=["status"])
        # F-12: semantic audit event for field-finding submission. The
        # middleware excludes the /findings/ suffix, so this is the only
        # audit record for this action. The event is logged AFTER the
        # finding and any status transition are persisted, so a failed
        # save would not produce a misleading success event. The metadata
        # is minimal and non-sensitive (task id, finding id, previous
        # status, transition) — observations and free-text fields are
        # NOT included.
        log_audit_event(
            actor=request.user,
            action="task:finding",
            target=task,
            metadata={
                "task_id": task.id,
                "finding_id": finding.id,
                "previous_status": previous_status,
                "transitioned_to": task.status,
            },
        )
        messages.success(request, "Field findings saved (internal record only).")
        return redirect("tasks:detail", pk=task.pk)


class TaskCompleteView(LoginRequiredMixin, View):
    """Mark a follow-up task as completed.

    Phase D (D-09): completion is permitted only from ASSIGNED or
    IN_PROGRESS. Completing a task in COMPLETED, VERIFIED, CLOSED, or
    CANCELLED is rejected with 403; the task status is unchanged.

    Phase D (R-1): only application officers may complete tasks. Task
    ownership alone is not sufficient.
    """

    # D-09: valid source states for completion.
    _VALID_COMPLETE_STATES = frozenset({
        FollowUpTask.Status.ASSIGNED,
        FollowUpTask.Status.IN_PROGRESS,
    })

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        task = get_object_or_404(FollowUpTask, pk=pk)
        # R-1: require is_officer() — task ownership alone is not sufficient.
        if not request.user.is_officer():
            raise PermissionDenied("Only extension officers and supervisors can complete tasks.")
        # D-09: reject completion from invalid source states.
        if task.status not in self._VALID_COMPLETE_STATES:
            raise PermissionDenied(
                f"Cannot complete a task in '{task.status}' status. "
                "Tasks can only be completed from 'assigned' or 'in_progress' status."
            )
        previous_status = task.status
        task.status = FollowUpTask.Status.COMPLETED
        task.save(update_fields=["status"])
        # F-12: semantic audit event for task completion. The middleware
        # excludes the /complete/ suffix, so this is the only audit record
        # for this action. Logged AFTER task.save() so a failed save would
        # not produce a misleading success event. Metadata is minimal and
        # non-sensitive (task id, previous status, new status).
        log_audit_event(
            actor=request.user,
            action="task:complete",
            target=task,
            metadata={
                "task_id": task.id,
                "previous_status": previous_status,
                "new_status": task.status,
            },
        )
        messages.success(request, "Task marked completed — awaiting supervisor verification if required.")
        return redirect("tasks:detail", pk=task.pk)


class TaskVerifyView(LoginRequiredMixin, View):
    """Supervisor verifies field findings — submitter cannot verify their own work.

    Phase D (D-08): verification is permitted only from COMPLETED, and
    at least one field finding must exist. Verifying a task in ASSIGNED,
    IN_PROGRESS, VERIFIED, CLOSED, or CANCELLED is rejected with 403.
    Verifying a COMPLETED task with no findings is also rejected. On
    rejection, the task status and finding verification metadata are
    unchanged.

    The existing ``is_superuser`` exception (line 154) is preserved per
    the approved policy (P-07 deferred). The existing self-verification
    restriction (submitter cannot verify their own latest finding) is
    also preserved.

    Phase 4 (atomicity): ``post`` is wrapped in ``@transaction.atomic``
    so that the task status change (``task.save``) and the finding
    verification metadata update (``finding.save``) commit or roll back
    together. If ``finding.save`` fails after ``task.save`` succeeds,
    the transaction rolls back the task status change — the task
    remains COMPLETED and the finding's ``verified_by`` / ``verified_at``
    remain unchanged. This addresses the partial-write risk identified
    in the Phase 4 read-only review.

    Limitation: ``log_audit_event`` swallows its own exceptions (per
    the established "audit must never break the call" convention in
    ``apps/audit/service.py``). The ``@transaction.atomic`` wrapper
    cannot detect an audit-write failure to roll back on, so a
    successful state change may still occur without a corresponding
    audit record if the audit write fails internally. This is the
    existing best-effort audit behaviour and is unchanged by Phase 4.
    """

    @transaction.atomic
    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        if request.user.role != User.Role.SUPERVISOR and not request.user.is_superuser:
            raise PermissionDenied("Only a supervisor can verify field findings.")
        task = get_object_or_404(FollowUpTask, pk=pk)
        # D-08: require COMPLETED status before verification.
        if task.status != FollowUpTask.Status.COMPLETED:
            raise PermissionDenied(
                f"Cannot verify a task in '{task.status}' status. "
                "Verification is only permitted for completed tasks."
            )
        finding = task.field_findings.order_by("-submitted_at").first()
        # D-08: require at least one finding before verification.
        if finding is None:
            raise PermissionDenied(
                "Cannot verify a task with no field findings. "
                "At least one finding must be submitted before verification."
            )
        if finding.submitted_by_id == request.user.id:
            raise PermissionDenied("You cannot verify your own field findings.")
        task.status = FollowUpTask.Status.VERIFIED
        task.save(update_fields=["status"])
        finding.verified_by = request.user
        finding.verified_at = timezone.now()
        finding.save(update_fields=["verified_by", "verified_at"])
        # F-12: semantic audit event for task verification. The middleware
        # excludes the /verify/ suffix, so this is the only audit record
        # for this action. Logged AFTER both task.save() and finding.save()
        # so a failed save would not produce a misleading success event.
        # Metadata is minimal and non-sensitive (task id, finding id,
        # verifier id) — observations are NOT included.
        log_audit_event(
            actor=request.user,
            action="task:verify",
            target=task,
            metadata={
                "task_id": task.id,
                "finding_id": finding.id,
                "verified_by_id": request.user.id,
            },
        )
        messages.success(request, "Task verified.")
        return redirect("tasks:detail", pk=task.pk)
