from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from apps.accounts.models import User

from .forms import FieldFindingForm, TaskStatusForm
from .models import FieldFinding, FollowUpTask


class FollowUpTaskListView(LoginRequiredMixin, ListView):
    model = FollowUpTask
    template_name = "tasks/list.html"
    context_object_name = "tasks"
    paginate_by = 25

    def get_queryset(self):
        return FollowUpTask.objects.select_related("approved_advisory__cluster", "owner").order_by("-created_at")


class FollowUpTaskDetailView(LoginRequiredMixin, DetailView):
    model = FollowUpTask
    template_name = "tasks/detail.html"
    context_object_name = "task"

    def get_queryset(self):
        return FollowUpTask.objects.select_related(
            "approved_advisory__cluster",
            "owner",
        ).prefetch_related("field_findings")


class TaskFieldFindingView(LoginRequiredMixin, View):
    """Record internal field findings — does not send farmer messages."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse | HttpResponseRedirect:
        task = get_object_or_404(FollowUpTask, pk=pk)
        if not (request.user.is_officer() or task.owner_id == request.user.id):
            raise PermissionDenied("Only the assignee or an officer can submit field findings.")
        form = FieldFindingForm(request.POST)
        if not form.is_valid():
            return render(request, "tasks/detail.html", {"task": task, "finding_form": form})
        finding = form.save(commit=False)
        finding.task = task
        finding.submitted_by = request.user
        finding.checklist = {
            "onset_verified_locally": request.POST.get("onset_verified_locally") == "yes",
            "pest_scouting_done": request.POST.get("pest_scouting_done") == "yes",
        }
        finding.save()
        if task.status == FollowUpTask.Status.ASSIGNED:
            task.status = FollowUpTask.Status.IN_PROGRESS
            task.save(update_fields=["status"])
        messages.success(request, "Field findings saved (internal record only).")
        return redirect("tasks:detail", pk=task.pk)


class TaskCompleteView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        task = get_object_or_404(FollowUpTask, pk=pk)
        if not (request.user.is_officer() or task.owner_id == request.user.id):
            raise PermissionDenied
        task.status = FollowUpTask.Status.COMPLETED
        task.save(update_fields=["status"])
        messages.success(request, "Task marked completed — awaiting supervisor verification if required.")
        return redirect("tasks:detail", pk=task.pk)


class TaskVerifyView(LoginRequiredMixin, View):
    """Supervisor verifies field findings — submitter cannot verify their own work."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        if request.user.role != User.Role.SUPERVISOR and not request.user.is_superuser:
            raise PermissionDenied("Only a supervisor can verify field findings.")
        task = get_object_or_404(FollowUpTask, pk=pk)
        finding = task.field_findings.order_by("-submitted_at").first()
        if finding and finding.submitted_by_id == request.user.id:
            raise PermissionDenied("You cannot verify your own field findings.")
        task.status = FollowUpTask.Status.VERIFIED
        task.save(update_fields=["status"])
        if finding:
            finding.verified_by = request.user
            finding.verified_at = timezone.now()
            finding.save(update_fields=["verified_by", "verified_at"])
        messages.success(request, "Task verified.")
        return redirect("tasks:detail", pk=task.pk)
