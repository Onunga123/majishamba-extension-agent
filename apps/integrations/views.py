"""Views for officer-supplied data ingestion.

These are the honest paths for getting real KMD bulletins and pest notices
into the system. The officer manually reads the official publication, then
transcribes the metadata into the form. We do NOT auto-fetch.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.accounts.permissions import require_officer

from .forms import KMDBulletinForm, OfficerFieldReportForm, PublishedPestNoticeForm
from .kmd import ingest_kmd_bulletin_metadata
from .pests import ingest_officer_field_report, ingest_published_notice_metadata


class IntegrationsIndexView(LoginRequiredMixin, View):
    """Landing page for officer-supplied data ingestion."""
    def get(self, request):
        require_officer(request.user)
        from apps.weather.models import WeatherSignal
        from apps.pests.models import PestAlert
        # Recent source records for the source register
        recent_weather = list(
            WeatherSignal.objects
            .exclude(synthetic_flag="synthetic")
            .order_by("-publication_date", "-retrieved_at")[:10]
        )
        recent_pests = list(
            PestAlert.objects
            .exclude(synthetic_flag="synthetic")
            .order_by("-publication_date", "-retrieved_at")[:10]
        )
        return render(request, "integrations/index.html", {
            "kmd_form_url": reverse("integrations:kmd_ingest"),
            "pest_report_url": reverse("integrations:pest_report"),
            "pest_notice_url": reverse("integrations:pest_notice"),
            "recent_weather": recent_weather,
            "recent_pests": recent_pests,
            "verification_labels": {
                "current_official": "Current official source",
                "regional_context": "Regional context",
                "officer_field_report": "Officer field report",
                "background_reference": "Background reference",
                "historical": "Historical (no longer current)",
                "synthetic": "Synthetic test scenario",
                "no_current_notice": "No current notice",
            },
        })


class KMDBulletinIngestView(LoginRequiredMixin, View):
    """Officer transcribes metadata from a KMD bulletin they've manually read."""
    def get(self, request):
        require_officer(request.user)
        form = KMDBulletinForm()
        return render(request, "integrations/kmd_ingest.html", {"form": form})

    def post(self, request):
        require_officer(request.user)
        form = KMDBulletinForm(request.POST)
        if not form.is_valid():
            return render(request, "integrations/kmd_ingest.html", {"form": form})
        data = form.cleaned_data
        # Validate: if rainfall_mm is provided, rainfall_period_note is required.
        if data.get("rainfall_mm") is not None and not data.get("rainfall_period_note"):
            form.add_error("rainfall_period_note", "This field is required when you enter a rainfall value.")
            return render(request, "integrations/kmd_ingest.html", {"form": form})
        try:
            result = ingest_kmd_bulletin_metadata(
                area_label=data["area_label"],
                period=data["period"],
                product_type=data["product_type"],
                publication_date=data["publication_date"],
                valid_from=data.get("valid_from"),
                valid_to=data.get("valid_to"),
                geographic_scope=data.get("geographic_scope", ""),
                coverage_level=data["coverage_level"],
                forecast_summary=data["forecast_summary"],
                rainfall_mm=data.get("rainfall_mm"),
                rainfall_period_note=data.get("rainfall_period_note", ""),
                onset_status=data["onset_status"],
                source_url=data.get("source_url", ""),
                actor_id=request.user.id,
            )
            if not result.get("is_valid", True):
                # Content validation failed — record was stored as review_required.
                # Show the officer the validation errors so they can fix and re-submit.
                for err in result.get("validation_errors", []):
                    messages.error(request, f"Validation: {err}")
                for warn in result.get("validation_warnings", []):
                    messages.warning(request, f"Warning: {warn}")
                messages.warning(
                    request,
                    f"Bulletin stored as WeatherSignal #{result['weather_signal_id']} with status 'review_required'. "
                    f"Fix the issues and re-submit, or ask a supervisor to review."
                )
            else:
                for warn in result.get("validation_warnings", []):
                    messages.warning(request, f"Warning: {warn}")
                messages.success(
                    request,
                    f"KMD bulletin ingested as WeatherSignal #{result['weather_signal_id']} "
                    f"({result['display_label']}). Dashboard now shows it as current."
                )
            return redirect("dashboard:home")
        except ValueError as exc:
            form.add_error(None, str(exc))
            return render(request, "integrations/kmd_ingest.html", {"form": form})


class OfficerFieldReportView(LoginRequiredMixin, View):
    """Officer submits a verified local pest field report."""
    def get(self, request):
        require_officer(request.user)
        form = OfficerFieldReportForm(initial={"observation_date": ""})
        return render(request, "integrations/pest_report.html", {"form": form})

    def post(self, request):
        require_officer(request.user)
        form = OfficerFieldReportForm(request.POST)
        if not form.is_valid():
            return render(request, "integrations/pest_report.html", {"form": form})
        data = form.cleaned_data
        result = ingest_officer_field_report(
            officer_author_name=request.user.display_name(),
            observation_date=data["observation_date"],
            coverage=data["coverage"],
            coverage_level=data["coverage_level"],
            pest=data["pest"],
            crop=data["crop"],
            severity=data["severity"],
            advisory=data.get("advisory", ""),
            actor_id=request.user.id,
        )
        messages.success(request, f"Officer field report ingested as PestAlert #{result['pest_alert_id']} (verification_status: {result['verification_status']}).")
        return redirect("dashboard:home")


class PublishedPestNoticeView(LoginRequiredMixin, View):
    """Officer transcribes metadata from a published official pest notice."""
    def get(self, request):
        require_officer(request.user)
        form = PublishedPestNoticeForm()
        return render(request, "integrations/pest_notice.html", {"form": form})

    def post(self, request):
        require_officer(request.user)
        form = PublishedPestNoticeForm(request.POST)
        if not form.is_valid():
            return render(request, "integrations/pest_notice.html", {"form": form})
        data = form.cleaned_data
        result = ingest_published_notice_metadata(
            authority=data["authority"],
            product_type=data["product_type"],
            publication_date=data["publication_date"],
            pest=data["pest"],
            crop=data["crop"],
            severity=data["severity"],
            geographic_scope=data.get("geographic_scope", ""),
            coverage_level=data["coverage_level"],
            source_url=data.get("source_url", ""),
            source_document_id=data.get("source_document_id", ""),
            actor_id=request.user.id,
        )
        messages.success(request, f"Published notice ingested as PestAlert #{result['pest_alert_id']} (verification_status: {result['verification_status']}).")
        return redirect("dashboard:home")
