"""Views for advisories."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import DetailView, ListView, View

from apps.accounts.permissions import require_officer
from apps.agents.models import AdvisoryRun
from apps.agents.run_worker import start_advisory_run_async
from apps.clusters.models import FarmerCluster

from .context_helpers import advisory_review_context
from .models import Advisory


class AdvisoryListView(LoginRequiredMixin, ListView):
    model = Advisory
    template_name = "advisories/list.html"
    context_object_name = "advisories"
    paginate_by = 20


class AdvisoryDetailView(LoginRequiredMixin, DetailView):
    model = Advisory
    template_name = "advisories/detail.html"
    context_object_name = "advisory"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(advisory_review_context(self.object))
        return ctx


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
