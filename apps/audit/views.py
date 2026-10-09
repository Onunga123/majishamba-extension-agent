from __future__ import annotations

import csv
import datetime as dt
import re

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.views import View
from django.views.generic import ListView

from .models import AuditEvent


# Human-readable action labels for the activity view
_ACTION_LABELS = {
    "account:register": "Account registered",
    "account:login": "Signed in",
    "account:logout": "Signed out",
    "account:approve": "Account approved",
    "account:reject": "Account rejected",
    "officer_approval": "Advisory reviewed",
    "advisory:request": "Advisory requested",
    "advisory:approve": "Advisory approved",
    "advisory:reject": "Advisory rejected",
    "advisory:soft_delete": "Advisory deleted",
    "advisory:restore": "Advisory restored",
    "advisory:edit": "Advisory edited",
    "task:complete": "Task completed",
    "task:verify": "Task verified",
    "task:finding": "Field findings submitted",
    "create_follow_up_task": "Follow-up task created",
    "agent_run:start": "Advisory generation started",
    "agent_run:end": "Advisory generation completed",
    "agent_run:failure": "Advisory generation failed",
    "ingest:open_meteo_forecast": "Open-Meteo forecast ingested",
    "ingest:kmd_bulletin": "KMD bulletin ingested",
    "ingest:officer_pest_report": "Pest field report submitted",
    "ingest:published_pest_notice": "Published pest notice ingested",
    "ingest:kalro_bibliographic": "KALRO bibliographic info recorded",
    "ingest:kalro_factsheet": "KALRO factsheet ingested",
}


def _humanize_action(action: str) -> str:
    """Convert a raw action code to a human-readable label."""
    # Direct mapping
    if action in _ACTION_LABELS:
        return _ACTION_LABELS[action]
    # HTTP method:path patterns
    if action.startswith("http:"):
        return _humanize_http_action(action)
    # Tool calls
    if action.startswith("tool:"):
        tool_name = action[5:]
        return f"Tool executed: {tool_name.replace('_', ' ')}"
    # Unknown — return as-is
    return action


def _humanize_http_action(action: str) -> tuple[str, str]:
    """Convert http:METHOD:/path/ to a human-readable phrase + object label."""
    m = re.match(r"http:(\w+):(.*)", action)
    if not m:
        return ("HTTP request", "")
    method, path = m.group(1), m.group(2)
    m = re.match(r"/advisories/(\d+)/restore/?$", path)
    if m:
        return ("Advisory restored", f"Advisory {m.group(1)}")
    m = re.match(r"/advisories/(\d+)/delete/?$", path)
    if m:
        return ("Advisory deleted", f"Advisory {m.group(1)}")
    m = re.match(r"/advisories/(\d+)/edit/?$", path)
    if m:
        return ("Advisory edited", f"Advisory {m.group(1)}")
    m = re.match(r"/advisories/request/?$", path)
    if m:
        return ("Advisory requested", "")
    m = re.match(r"/approvals/(\d+)/?$", path)
    if m:
        return ("Advisory reviewed", f"Advisory {m.group(1)}")
    m = re.match(r"/tasks/(\d+)/complete/?$", path)
    if m:
        return ("Task completed", f"Task {m.group(1)}")
    m = re.match(r"/tasks/(\d+)/verify/?$", path)
    if m:
        return ("Task verified", f"Task {m.group(1)}")
    m = re.match(r"/tasks/(\d+)/findings/?$", path)
    if m:
        return ("Field findings submitted", f"Task {m.group(1)}")
    if "/accounts/login" in path:
        return ("Signed in", "")
    if "/accounts/logout" in path:
        return ("Signed out", "")
    if "/accounts/register" in path:
        return ("Account registered", "")
    return (f"HTTP {method} request", path)


def _is_technical_event(action: str) -> bool:
    """Determine if an event is a technical/system event (not a human activity)."""
    return (
        action.startswith("tool:")
        or action.startswith("agent_run:")
        or action.startswith("http:")
    )


def _approval_label(event: AuditEvent) -> str:
    """Derive a meaningful approval-status label from the event."""
    if event.approval_status:
        # Map to readable labels
        status_map = {
            "approved": "Approved",
            "rejected": "Rejected",
            "deferred": "Deferred",
            "needs_evidence": "Needs more evidence",
        }
        return status_map.get(event.approval_status, event.approval_status.title())
    # Check if this is an approval-related action
    approval_actions = {"officer_approval", "advisory:approve", "advisory:reject"}
    if event.action in approval_actions:
        return "Pending"  # Should have been set but wasn't — don't invent
    # Not an approval-related event
    return "Not applicable"


class AuditEventListView(LoginRequiredMixin, ListView):
    model = AuditEvent
    template_name = "audit/list.html"
    context_object_name = "events"
    paginate_by = 50

    def get_queryset(self):
        qs = AuditEvent.objects.select_related("actor").order_by("-created_at")

        # --- Search ---
        search_q = (self.request.GET.get("q") or "").strip()
        if search_q:
            qs = qs.filter(
                Q(action__icontains=search_q)
                | Q(target_type__icontains=search_q)
                | Q(target_id__icontains=search_q)
                | Q(actor__username__icontains=search_q)
                | Q(actor__full_name__icontains=search_q)
            )

        # --- Actor filter ---
        actor = self.request.GET.get("actor") or ""
        if actor:
            qs = qs.filter(actor__username=actor)

        # --- Action category filter ---
        category = self.request.GET.get("category") or ""
        if category == "human":
            qs = qs.exclude(action__startswith="tool:").exclude(action__startswith="agent_run:")
        elif category == "system":
            qs = qs.filter(
                Q(action__startswith="tool:") | Q(action__startswith="agent_run:")
            )
        elif category == "approval":
            qs = qs.filter(
                Q(action__in=["officer_approval", "advisory:approve", "advisory:reject"])
                | Q(approval_status__in=["approved", "rejected", "deferred", "needs_evidence"])
            )

        # --- Date range filter ---
        from_str = self.request.GET.get("from")
        to_str = self.request.GET.get("to")
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

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Add human-readable labels for each event
        formatted_events = []
        for e in ctx.get("events", []):
            action_human = _humanize_action(e.action)
            if e.action.startswith("http:"):
                _, obj_label = _humanize_http_action(e.action)
            else:
                obj_label = ""
                if e.target_type and e.target_id:
                    obj_label = f"{e.target_type} {e.target_id}"
                elif e.target_type:
                    obj_label = e.target_type
            formatted_events.append({
                "event": e,
                "action_human": action_human,
                "object_label": obj_label,
                "is_technical": _is_technical_event(e.action),
                "approval_label": _approval_label(e),
                "actor_display": e.actor.display_name() if e.actor else "system",
            })
        ctx["formatted_events"] = formatted_events
        ctx["search_q"] = self.request.GET.get("q", "")
        ctx["actor_filter"] = self.request.GET.get("actor", "")
        ctx["category_filter"] = self.request.GET.get("category", "")
        ctx["from_date"] = self.request.GET.get("from", "")
        ctx["to_date"] = self.request.GET.get("to", "")
        ctx["is_staff"] = self.request.user.is_staff
        return ctx


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
            "timestamp", "actor", "action", "human_readable_action",
            "tool_name", "target_type", "target_id",
            "approval_status", "approval_label",
            "inputs_summary", "outputs_summary",
        ])
        for e in qs:
            actor_name = e.actor.display_name() if e.actor else "system"
            # Sanitize text fields against spreadsheet formula injection
            def _sanitize(val):
                if isinstance(val, str) and val and val[0] in ("=", "+", "-", "@"):
                    return f"'{val}"
                return val

            writer.writerow([
                e.created_at.isoformat(),
                _sanitize(actor_name),
                _sanitize(e.action),
                _sanitize(_humanize_action(e.action)),
                _sanitize(e.tool_name),
                _sanitize(e.target_type),
                _sanitize(e.target_id),
                _sanitize(e.approval_status),
                _sanitize(_approval_label(e)),
                _sanitize(str(e.inputs_summary.get("value", "") if isinstance(e.inputs_summary, dict) else e.inputs_summary)[:500]),
                _sanitize(str(e.outputs_summary.get("value", "") if isinstance(e.outputs_summary, dict) else e.outputs_summary)[:500]),
            ])
        return response

