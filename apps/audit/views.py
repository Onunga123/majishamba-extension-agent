from __future__ import annotations

import csv
import datetime as dt

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.views import View
from django.views.generic import ListView

from .models import AuditEvent


class AuditEventListView(LoginRequiredMixin, ListView):
    model = AuditEvent
    template_name = "audit/list.html"
    context_object_name = "events"
    paginate_by = 50


class AuditEventCSVExportView(LoginRequiredMixin, View):
    """Export audit events as CSV for compliance review.

    Supports optional date-range filtering via ?from=YYYY-MM-DD&to=YYYY-MM-DD.
    Returns all events if no filter is provided.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        qs = AuditEvent.objects.select_related("actor").order_by("-created_at")
        # Optional date-range filter (by created_at date, not datetime).
        from_str = request.GET.get("from")
        to_str = request.GET.get("to")
        if from_str:
            try:
                from_date = dt.date.fromisoformat(from_str)
                qs = qs.filter(created_at__date__gte=from_date)
            except ValueError:
                pass
        if to_str:
            try:
                to_date = dt.date.fromisoformat(to_str)
                qs = qs.filter(created_at__date__lte=to_date)
            except ValueError:
                pass
        # Cap at 10000 rows to prevent accidental DoS.
        qs = qs[:10000]
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="kachieng_audit_trail.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "timestamp", "actor", "action", "tool_name",
            "target_type", "target_id", "approval_status",
            "inputs_summary", "outputs_summary",
        ])
        for e in qs:
            actor_name = e.actor.display_name() if e.actor else "system"
            writer.writerow([
                e.created_at.isoformat(),
                actor_name,
                e.action,
                e.tool_name,
                e.target_type,
                e.target_id,
                e.approval_status,
                (e.inputs_summary.get("value", "") if isinstance(e.inputs_summary, dict) else str(e.inputs_summary))[:500],
                (e.outputs_summary.get("value", "") if isinstance(e.outputs_summary, dict) else str(e.outputs_summary))[:500],
            ])
        return response

