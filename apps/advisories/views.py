"""Views for advisories."""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView, View

from apps.accounts.permissions import require_officer
from apps.agents.runner import run_advisory_pipeline
from apps.clusters.models import FarmerCluster

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


class AdvisoryEditView(LoginRequiredMixin, View):
    """Officer can edit a DRAFT advisory before approving it."""

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        require_officer(request.user)
        advisory = get_object_or_404(Advisory, pk=pk)
        from .forms import AdvisoryReviewForm

        form = AdvisoryReviewForm(instance=advisory)
        return render(request, "advisories/edit.html", {"advisory": advisory, "form": form})

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        require_officer(request.user)
        advisory = get_object_or_404(Advisory, pk=pk)
        from .forms import AdvisoryReviewForm

        form = AdvisoryReviewForm(request.POST, instance=advisory)
        if form.is_valid():
            form.save()
            return redirect("advisories:detail", pk=advisory.pk)
        return render(request, "advisories/edit.html", {"advisory": advisory, "form": form})


class RequestAdvisoryView(LoginRequiredMixin, View):
    """Officer requests a draft advisory for a Kachieng cluster. Kicks the agent."""

    def get(self, request: HttpRequest) -> HttpResponse:
        require_officer(request.user)
        clusters = FarmerCluster.objects.all().order_by("cluster_id")
        return render(request, "advisories/request.html", {"clusters": clusters})

    def post(self, request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
        require_officer(request.user)
        cluster_id = request.POST.get("cluster_id")
        cluster = get_object_or_404(FarmerCluster, cluster_id=cluster_id)
        result = run_advisory_pipeline(
            cluster_id=cluster.cluster_id,
            ward=cluster.ward.name,
            sub_county=cluster.ward.sub_county.name,
            county=cluster.ward.sub_county.county.name,
            actor=request.user,
        )
        if result.get("advisory_id"):
            return redirect("advisories:detail", pk=result["advisory_id"])
        return render(
            request,
            "advisories/request.html",
            {"clusters": FarmerCluster.objects.all(), "error": result.get("error", "Agent failed."),
             "trace": result.get("trace", [])},
        )
