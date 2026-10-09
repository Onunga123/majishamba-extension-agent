"""Views for advisories."""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import DetailView, ListView, View

from apps.accounts.permissions import require_officer
from apps.agents.models import AdvisoryRun
from apps.agents.run_worker import start_advisory_run_async
from apps.audit.service import log_audit_event
from apps.clusters.models import FarmerCluster

from .context_helpers import advisory_review_context
from .models import Advisory


class AdvisoryListView(LoginRequiredMixin, ListView):
    model = Advisory
    template_name = "advisories/list.html"
    context_object_name = "advisories"
    paginate_by = 20

    def get_queryset(self):
        qs = Advisory.objects.select_related("cluster").all()

        # --- Search ---
        search_q = (self.request.GET.get("q") or "").strip()
        if search_q:
            # Support searching by advisory ID (numeric), locality name, or cluster ID
            if search_q.isdigit():
                qs = qs.filter(id=int(search_q))
            else:
                qs = qs.filter(
                    Q(cluster__locality__icontains=search_q)
                    | Q(cluster__cluster_id__icontains=search_q)
                )

        # --- Status filter ---
        status = self.request.GET.get("status") or ""
        valid_statuses = {choice[0] for choice in Advisory.Status.choices}
        if status in valid_statuses:
            qs = qs.filter(status=status)

        # --- Sorting ---
        sort = self.request.GET.get("sort") or "-created_at"
        valid_sorts = {
            "-created_at", "created_at",
            "id", "-id",
            "cluster__locality", "-cluster__locality",
            "cluster__cluster_id", "-cluster__cluster_id",
            "status", "-status",
        }
        if sort not in valid_sorts:
            sort = "-created_at"
        qs = qs.order_by(sort)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["advisory_count"] = Advisory.objects.count()
        ctx["user_can_request_advisory"] = bool(
            self.request.user.is_authenticated and self.request.user.is_officer()
        )
        # Preserve search/filter/sort state for pagination links
        ctx["search_q"] = self.request.GET.get("q", "")
        ctx["status_filter"] = self.request.GET.get("status", "")
        ctx["sort"] = self.request.GET.get("sort", "-created_at")
        ctx["status_choices"] = Advisory.Status.choices
        return ctx


class AdvisoryDetailView(LoginRequiredMixin, DetailView):
    model = Advisory
    template_name = "advisories/detail.html"
    context_object_name = "advisory"

    def get_queryset(self):
        # Officers/supervisors can view deleted advisories (with a warning banner);
        # viewers can only see active ones.
        if self.request.user.is_authenticated and self.request.user.is_officer():
            return Advisory.all_objects.select_related("cluster", "created_by", "deleted_by")
        return Advisory.objects.select_related("cluster", "created_by")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(advisory_review_context(self.object))
        ctx["is_deleted"] = self.object.is_deleted
        return ctx


class AdvisorySoftDeleteView(LoginRequiredMixin, View):
    """Officer soft-deletes an advisory. Preserves the record for audit."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        require_officer(request.user)
        advisory = get_object_or_404(Advisory.all_objects, pk=pk)
        if advisory.is_deleted:
            messages.warning(request, "This advisory is already deleted.")
            return redirect("advisories:detail", pk=pk)
        reason = request.POST.get("deletion_reason", "")
        advisory.soft_delete(by_user=request.user, reason=reason)
        log_audit_event(
            actor=request.user,
            action="advisory:soft_delete",
            target=advisory,
            metadata={"reason": reason[:200], "advisory_id": advisory.id},
        )
        messages.success(request, f"Advisory {advisory.id} has been soft-deleted. It is preserved in the audit trail.")
        return redirect("advisories:list")


class AdvisoryRestoreView(LoginRequiredMixin, View):
    """Supervisor restores a soft-deleted advisory."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        from apps.accounts.permissions import require_approver
        require_approver(request.user)
        advisory = get_object_or_404(Advisory.all_objects, pk=pk)
        if not advisory.is_deleted:
            messages.warning(request, "This advisory is not deleted.")
            return redirect("advisories:detail", pk=pk)
        advisory.restore()
        log_audit_event(
            actor=request.user,
            action="advisory:restore",
            target=advisory,
            metadata={"advisory_id": advisory.id},
        )
        messages.success(request, f"Advisory {advisory.id} has been restored.")
        return redirect("advisories:detail", pk=pk)


class DeletedAdvisoryListView(LoginRequiredMixin, ListView):
    """Shows soft-deleted advisories. Supervisors and staff only."""
    template_name = "advisories/deleted.html"
    context_object_name = "advisories"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.can_approve()):
            return HttpResponseForbidden("Only supervisors can view deleted advisories.")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Advisory.all_objects.filter(deleted_at__isnull=False).select_related("cluster", "deleted_by").order_by("-deleted_at")


class AdvisoryEditView(LoginRequiredMixin, View):
    """Officer can edit a DRAFT advisory before approving it."""

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        require_officer(request.user)
        advisory = get_object_or_404(Advisory, pk=pk)
        if advisory.status != Advisory.Status.DRAFT:
            return render(
                request,
                "advisories/edit.html",
                {"advisory": advisory, "blocked": "Only DRAFT advisories can be edited. Create a new request instead."},
            )
        from .forms import AdvisoryReviewForm

        form = AdvisoryReviewForm(instance=advisory)
        ctx = {"advisory": advisory, "form": form}
        ctx.update(advisory_review_context(advisory))
        return render(request, "advisories/edit.html", ctx)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        require_officer(request.user)
        advisory = get_object_or_404(Advisory, pk=pk)
        if advisory.status != Advisory.Status.DRAFT:
            return redirect("advisories:detail", pk=advisory.pk)
        from .forms import AdvisoryReviewForm

        form = AdvisoryReviewForm(request.POST, instance=advisory)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.content_version = advisory.content_version + 1
            updated.save()
            return redirect("advisories:detail", pk=advisory.pk)
        ctx = {"advisory": advisory, "form": form}
        ctx.update(advisory_review_context(advisory))
        return render(request, "advisories/edit.html", ctx)


class RequestAdvisoryView(LoginRequiredMixin, View):
    """Officer requests a draft advisory for a Kachieng cluster."""

    def get(self, request: HttpRequest) -> HttpResponse:
        require_officer(request.user)
        clusters = FarmerCluster.objects.all().order_by("cluster_id")
        preselect = request.GET.get("cluster")
        return render(request, "advisories/request.html", {"clusters": clusters, "preselect": preselect})

    def post(self, request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
        require_officer(request.user)
        cluster_id = request.POST.get("cluster_id")
        cluster = get_object_or_404(FarmerCluster, cluster_id=cluster_id)

        cutoff = timezone.now() - timedelta(minutes=30)
        existing = (
            AdvisoryRun.objects.filter(
                requested_by=request.user,
                cluster=cluster,
                status__in=[
                    AdvisoryRun.Status.QUEUED,
                    AdvisoryRun.Status.RUNNING,
                    AdvisoryRun.Status.WAITING_FOR_MODEL,
                    AdvisoryRun.Status.VALIDATING,
                ],
                created_at__gte=cutoff,
            )
            .order_by("-created_at")
            .first()
        )
        if existing:
            return redirect("advisories:run_status", run_id=existing.run_id)

        run = AdvisoryRun.objects.create(
            requested_by=request.user,
            cluster=cluster,
            status=AdvisoryRun.Status.QUEUED,
            current_message="Queued — starting shortly",
        )
        start_advisory_run_async(run.pk)
        return redirect("advisories:run_status", run_id=run.run_id)


class AdvisoryRunStatusView(LoginRequiredMixin, View):
    """Officer-visible run progress (HTMX polls the partial)."""

    def get(self, request: HttpRequest, run_id) -> HttpResponse:
        run = get_object_or_404(AdvisoryRun.objects.select_related("cluster", "result_advisory"), run_id=run_id)
        if run.requested_by_id != request.user.id and not request.user.is_staff:
            return HttpResponseForbidden("You cannot view this run.")
        return render(request, "advisories/run_status.html", {"run": run})


class AdvisoryRunProgressPartialView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest, run_id) -> HttpResponse:
        run = get_object_or_404(AdvisoryRun.objects.select_related("cluster", "result_advisory"), run_id=run_id)
        if run.requested_by_id != request.user.id and not request.user.is_staff:
            return HttpResponseForbidden("You cannot view this run.")
        return render(request, "advisories/partials/run_progress.html", {"run": run})
