"""Officer dashboard views — map, cluster list, advisory review."""
from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import render
from django.views import View

from apps.advisories.models import Advisory, AdvisoryEvidence
from apps.audit.models import AuditEvent
from apps.clusters.models import FarmerCluster
from apps.integrations.kalro import permission_status as kalro_permission_status
from apps.integrations.kmd import no_current_kmd_notice
from apps.integrations.pests import no_current_pest_notice
from apps.pests.models import PestAlert
from apps.tasks.models import FollowUpTask
from apps.weather.models import WeatherSignal


# Status filter choices — also drives the template filter chips.
CLUSTER_STATUS_FILTERS = (
    ("all", "All"),
    ("draft", "Draft"),
    ("approved", "Approved"),
    ("needs_field_visit", "Needs field visit"),
    ("no_advisory", "No advisory"),
)

# Workflow status taxonomy used to label advisories and cluster rows.
# Maps Advisory.Status → (label, ai_label, human_state) for transparent UX.
WORKFLOW_STATUS = {
    Advisory.Status.DRAFT:        ("AI-generated draft", True,  "Human review required"),
    Advisory.Status.NEEDS_EVIDENCE: ("Needs more evidence", True, "Human review required"),
    Advisory.Status.APPROVED:    ("Human-approved",     False, "Field verification pending"),
    Advisory.Status.REJECTED:    ("Rejected by reviewer", False, "Closed"),
    Advisory.Status.DEFERRED:    ("Deferred",           False, "On hold"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evidence_quality(advisory) -> str:
    """Return one of: 'Strong', 'Moderate', 'Limited', 'Insufficient'.

    Heuristic (no fake confidence scores):
        - Strong:     ≥3 evidence rows, none stale, weather + at least one of (pest|market) present
        - Moderate:   ≥2 evidence rows, none stale
        - Limited:    ≥1 evidence row, or some stale evidence
        - Insufficient: 0 evidence rows

    This is a deterministic, explainable heuristic — not a probabilistic score.
    """
    evidence = list(advisory.evidence.all())
    n = len(evidence)
    if n == 0:
        return "Insufficient"
    stale_count = sum(1 for e in evidence if e.is_stale)
    source_types = {e.source_type for e in evidence}
    has_weather = "weather" in source_types
    has_pest_or_market = "pest" in source_types or "market" in source_types
    if n >= 3 and stale_count == 0 and has_weather and has_pest_or_market:
        return "Strong"
    if n >= 2 and stale_count == 0:
        return "Moderate"
    return "Limited"


def _audit_timeline(event: AuditEvent) -> dict:
    """Format one AuditEvent as a 'Who | What | Object | When | Result' row.

    Returns a dict with: actor, action_human, object_label, when_display,
    result_badge, raw_action (for staff-only technical views).
    """
    # Map internal action codes to human-readable text
    action_map = {
        "account:register": "registered an account",
        "account:login": "signed in",
        "account:approve": "approved an account",
        "account:reject": "rejected an account",
        "officer_approval": "reviewed an advisory",
        "advisory:request": "requested an advisory",
        "advisory:approve": "approved an advisory",
        "advisory:reject": "rejected an advisory",
        "advisory:delete": "deleted an advisory",
        "advisory:restore": "restored an advisory",
        "advisory:edit": "edited an advisory",
        "task:complete": "completed a task",
        "task:verify": "verified a task",
        "task:finding": "submitted field findings",
        "tool:call": "called a tool",
    }
    action_human = action_map.get(event.action, event.action)
    # Object label: try metadata or target_type
    obj_label = ""
    if event.target_type:
        obj_label = f"{event.target_type}"
        if event.target_id:
            obj_label = f"{event.target_type} #{event.target_id}"
    elif event.metadata and "advisory_id" in event.metadata:
        obj_label = f"Advisory #{event.metadata['advisory_id']}"
    elif event.metadata and "username" in event.metadata:
        obj_label = f"account '{event.metadata['username']}'"
    # Result badge: derive from action
    result_badge = ""
    if "approve" in event.action:
        result_badge = "approved"
    elif "reject" in event.action:
        result_badge = "rejected"
    elif "delete" in event.action:
        result_badge = "deleted"
    elif "complete" in event.action:
        result_badge = "completed"
    elif "verify" in event.action:
        result_badge = "verified"
    elif "login" in event.action:
        result_badge = "session started"
    elif "register" in event.action:
        result_badge = "pending review"
    elif "edit" in event.action:
        result_badge = "edited"

    actor_name = event.actor.get_username() if event.actor else "system"
    return {
        "actor": event.actor,
        "actor_name": actor_name,
        "action_human": action_human,
        "object_label": obj_label,
        "when_display": event.created_at,
        "when_iso": event.created_at.isoformat() if event.created_at else "",
        "result_badge": result_badge,
        "raw_action": event.action,  # kept for staff-only technical view
    }


def _cluster_next_action(cluster, advisory_q) -> str:
    """Return a short string describing the next action for a cluster."""
    latest = advisory_q.order_by("-created_at").first()
    if latest is None:
        return "Request advisory"
    s = latest.status
    if s == Advisory.Status.DRAFT:
        return "Review draft"
    if s == Advisory.Status.APPROVED:
        has_open_task = latest.follow_up_tasks.exclude(
            status__in=[FollowUpTask.Status.COMPLETED, FollowUpTask.Status.VERIFIED,
                        FollowUpTask.Status.CLOSED, FollowUpTask.Status.CANCELLED]
        ).exists()
        return "Field visit" if has_open_task else "Approved"
    if s == Advisory.Status.NEEDS_EVIDENCE:
        return "Re-evidence"
    if s == Advisory.Status.REJECTED:
        return "Reconsider"
    if s == Advisory.Status.DEFERRED:
        return "Deferred"
    return "Review"


def _cluster_filter_to_status(cluster_stats: list[dict], status_filter: str) -> list[dict]:
    if status_filter == "all":
        return cluster_stats
    if status_filter == "draft":
        return [c for c in cluster_stats if c["draft_count"] > 0]
    if status_filter == "approved":
        return [c for c in cluster_stats if c["approved_count"] > 0]
    if status_filter == "needs_field_visit":
        return [c for c in cluster_stats if c["next_action"] == "Field visit"]
    if status_filter == "no_advisory":
        return [c for c in cluster_stats if c["advisory_count"] == 0]
    return cluster_stats


def _latest_real_weather():
    return (
        WeatherSignal.objects
        .exclude(synthetic_flag="synthetic")
        .exclude(verification_status="review_required")
        .order_by("-publication_date", "-source_date", "-retrieved_at")
        .first()
    )


def _latest_synthetic_weather():
    return (
        WeatherSignal.objects
        .filter(synthetic_flag="synthetic")
        .order_by("-publication_date", "-source_date", "-retrieved_at")
        .first()
    )


def _latest_real_pest_notice():
    return (
        PestAlert.objects
        .exclude(synthetic_flag="synthetic")
        .filter(verification_status__in=["current_official", "officer_field_report"])
        .order_by("-publication_date", "-source_date", "-retrieved_at")
        .first()
    )


def _latest_synthetic_pest_notice():
    return (
        PestAlert.objects
        .filter(synthetic_flag="synthetic")
        .order_by("-publication_date", "-source_date", "-retrieved_at")
        .first()
    )


# ---------------------------------------------------------------------------
# Main dashboard view
# ---------------------------------------------------------------------------

class DashboardHomeView(LoginRequiredMixin, View):
    def get(self, request):
        # --- Search + filter params ---
        search_q = (request.GET.get("q") or "").strip()
        status_filter = request.GET.get("status") or "all"
        if status_filter not in {value for value, _ in CLUSTER_STATUS_FILTERS}:
            status_filter = "all"

        can_request_advisory = bool(request.user.is_authenticated and request.user.is_officer())
        can_approve = bool(request.user.is_authenticated and request.user.can_approve())

        # --- Cluster list (with optional search) ---
        cluster_qs = FarmerCluster.objects.select_related("ward__sub_county__county").all()
        if search_q:
            cluster_qs = cluster_qs.filter(
                Q(name__icontains=search_q) | Q(cluster_id__icontains=search_q) | Q(locality__icontains=search_q)
            )
        clusters = list(cluster_qs)

        cluster_stats = []
        for c in clusters:
            advisory_q = c.advisories.all()
            latest = advisory_q.order_by("-created_at").first()
            cluster_stats.append({
                "cluster": c,
                "household_count": c.households.count(),
                "plot_count": sum(h.plots.count() for h in c.households.all()),
                "advisory_count": advisory_q.count(),
                "draft_count": advisory_q.filter(status=Advisory.Status.DRAFT).count(),
                "approved_count": advisory_q.filter(status=Advisory.Status.APPROVED).count(),
                "next_action": _cluster_next_action(c, advisory_q),
                "latest_advisory_status": latest.status if latest else None,
                "latest_advisory_updated": latest.created_at if latest else None,
            })

        filtered_cluster_stats = _cluster_filter_to_status(cluster_stats, status_filter)

        # --- Needs Your Attention ---
        # 4 actionable categories: drafts awaiting review, field visits required,
        # pending tasks, recently approved advisories.
        drafts_awaiting_review = list(
            Advisory.objects
            .select_related("cluster")
            .filter(status=Advisory.Status.DRAFT)
            .order_by("-created_at")[:5]
        )
        # Field visits required = approved advisories with open follow-up tasks
        field_visit_advisories = list(
            Advisory.objects
            .select_related("cluster")
            .filter(status=Advisory.Status.APPROVED)
            .filter(
                follow_up_tasks__status__in=[
                    FollowUpTask.Status.ASSIGNED,
                    FollowUpTask.Status.IN_PROGRESS,
                ]
            )
            .distinct()
            .order_by("-created_at")[:5]
        )
        pending_tasks_for_attention = list(
            FollowUpTask.objects
            .exclude(status__in=[FollowUpTask.Status.COMPLETED, FollowUpTask.Status.VERIFIED,
                                  FollowUpTask.Status.CLOSED, FollowUpTask.Status.CANCELLED])
            .select_related("approved_advisory__cluster")
            .order_by("deadline")[:5]
        )
        recently_approved = list(
            Advisory.objects
            .select_related("cluster")
            .filter(status=Advisory.Status.APPROVED)
            .order_by("-updated_at")[:5]
        )

        needs_attention = {
            "drafts_awaiting_review": drafts_awaiting_review,
            "drafts_count": Advisory.objects.filter(status=Advisory.Status.DRAFT).count(),
            "field_visits_required": field_visit_advisories,
            "field_visits_count": len(field_visit_advisories),
            "pending_tasks": pending_tasks_for_attention,
            "pending_tasks_count": FollowUpTask.objects.exclude(
                status__in=[FollowUpTask.Status.COMPLETED, FollowUpTask.Status.VERIFIED,
                             FollowUpTask.Status.CLOSED, FollowUpTask.Status.CANCELLED]
            ).count(),
            "recently_approved": recently_approved,
            "recently_approved_count": Advisory.objects.filter(status=Advisory.Status.APPROVED).count(),
        }

        # --- Recent advisories grouped by status (limit 5–7 each) ---
        recent_advisories_qs = Advisory.objects.select_related("cluster").order_by("-created_at")
        advisories_by_status = {
            "draft": list(recent_advisories_qs.filter(status=Advisory.Status.DRAFT)[:7]),
            "approved": list(recent_advisories_qs.filter(status=Advisory.Status.APPROVED)[:7]),
            "rejected": list(recent_advisories_qs.filter(status=Advisory.Status.REJECTED)[:7]),
        }

        # --- Pending tasks: short summary, 5 max ---
        pending_tasks = list(
            FollowUpTask.objects
            .exclude(status__in=[FollowUpTask.Status.COMPLETED, FollowUpTask.Status.VERIFIED,
                                  FollowUpTask.Status.CLOSED, FollowUpTask.Status.CANCELLED])
            .select_related("approved_advisory__cluster")
            .order_by("deadline")[:5]
        )

        # --- Recent activity timeline (5 max, decision-oriented, no tool:*) ---
        recent_event_qs = (
            AuditEvent.objects
            .select_related("actor")
            .exclude(action__startswith="tool:")
            .order_by("-created_at")[:5]
        )
        recent_events = [_audit_timeline(e) for e in recent_event_qs]

        # Badges for the nav and dashboard
        draft_advisory_count = needs_attention["drafts_count"]
        pending_task_count = needs_attention["pending_tasks_count"]

        # --- Honest weather state ---
        real_weather = _latest_real_weather()
        synthetic_weather = _latest_synthetic_weather()
        if real_weather:
            weather_panel = {
                "kind": "real",
                "signal": real_weather,
                "rainfall_display": real_weather.rainfall_display,
                "is_regional": real_weather.is_regional_context,
            }
        else:
            weather_panel = {
                "kind": "no_current_notice",
                "no_notice": no_current_kmd_notice(),
                "synthetic_for_demo": synthetic_weather,
            }

        # --- Honest pest state ---
        real_pest = _latest_real_pest_notice()
        synthetic_pest = _latest_synthetic_pest_notice()
        if real_pest:
            pest_panel = {
                "kind": "real",
                "alert": real_pest,
                "severity_display": real_pest.severity_display_safe,
            }
        else:
            pest_panel = {
                "kind": "no_current_notice",
                "no_notice": no_current_pest_notice(),
                "synthetic_for_demo": synthetic_pest,
            }

        # --- KALRO permission state ---
        kalro_state = kalro_permission_status()

        # --- Last updated timestamp (for header) ---
        last_updated = dt.datetime.now()

        return render(
            request,
            "dashboard/home.html",
            {
                # Header
                "ward": "Kachieng",
                "sub_county": "Nyatike",
                "county": "Migori",
                "last_updated": last_updated,
                # User
                "can_request_advisory": can_request_advisory,
                "can_approve": can_approve,
                # Clusters
                "clusters": clusters,
                "cluster_stats": filtered_cluster_stats,
                "cluster_count": len(clusters),
                "filtered_cluster_count": len(filtered_cluster_stats),
                "search_q": search_q,
                "status_filter": status_filter,
                "status_filter_choices": CLUSTER_STATUS_FILTERS,
                # Needs attention
                "needs_attention": needs_attention,
                # Advisories
                "advisories_by_status": advisories_by_status,
                "workflow_status": WORKFLOW_STATUS,
                # Tasks
                "pending_tasks": pending_tasks,
                # Audit
                "recent_events": recent_events,
                # Badges
                "draft_advisory_count": draft_advisory_count,
                "pending_task_count": pending_task_count,
                # Weather / pests / guidance
                "weather_panel": weather_panel,
                "pest_panel": pest_panel,
                "kalro_state": kalro_state,
            },
        )


# ---------------------------------------------------------------------------
# Map / Audit / About / Guidance / DataSources views
# ---------------------------------------------------------------------------

class ClusterMapView(LoginRequiredMixin, View):
    def get(self, request):
        clusters = list(FarmerCluster.objects.select_related("ward__sub_county__county", "locality_coordinate").all())
        mapped_count = 0
        unmapped_count = 0
        localities_for_template: list[dict] = []
        for c in clusters:
            has_coord = (
                hasattr(c, "locality_coordinate")
                and c.locality_coordinate.verification_status == "approved"
                and c.locality_coordinate.coordinate_type != "synthetic"
            )
            if has_coord:
                lc = c.locality_coordinate
                localities_for_template.append({
                    "cluster_id": c.cluster_id,
                    "name": c.name,
                    "locality": c.locality or lc.locality_name,
                    "lat": lc.latitude,
                    "lon": lc.longitude,
                    "coordinate_type": lc.coordinate_type,
                    "coordinate_source": lc.coordinate_source,
                    "source_url": lc.source_url,
                    "households": c.households.count(),
                    "verified_by": lc.verified_by,
                    "has_real_coords": True,
                })
                mapped_count += 1
            else:
                localities_for_template.append({
                    "cluster_id": c.cluster_id,
                    "name": c.name,
                    "locality": c.locality or "",
                    "lat": None,
                    "lon": None,
                    "households": c.households.count(),
                    "has_real_coords": False,
                    "notes": "Coordinates not yet recorded" if not hasattr(c, "locality_coordinate") else f"Awaiting review (status: {c.locality_coordinate.verification_status})",
                })
                unmapped_count += 1
        cfg = settings.MAJISHAMBA
        tile_url = cfg.get("MAP_BASEMAP_TILES", "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png")
        api_key = cfg.get("MAP_API_KEY", "")
        if api_key and "{api_key}" in tile_url:
            tile_url = tile_url.replace("{api_key}", api_key)
        tile_url = tile_url.replace("{r}", "")
        return render(request, "dashboard/map.html", {
            "clusters": clusters,
            "localities": localities_for_template,
            "mapped_count": mapped_count,
            "unmapped_count": unmapped_count,
            "total_count": len(clusters),
            "tile_url": tile_url,
            "attribution": cfg.get("MAP_BASEMAP_ATTRIBUTION", "© Stadia Maps © OpenMapTiles © OpenStreetMap contributors"),
            "max_zoom": cfg.get("MAP_MAX_ZOOM", 20),
            "can_request_advisory": bool(request.user.is_authenticated and request.user.is_officer()),
        })


class AuditTrailView(LoginRequiredMixin, View):
    def get(self, request):
        events_qs = AuditEvent.objects.select_related("actor").order_by("-created_at")[:200]
        # Format as timeline for the audit page
        events = [_audit_timeline(e) for e in events_qs]
        # Staff-only: also expose raw audit events for technical view
        raw_events = list(events_qs) if request.user.is_staff else None
        return render(request, "dashboard/audit.html", {
            "events": events,
            "raw_events": raw_events,
        })


class AboutView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, "dashboard/about.html", {})


class GuidanceView(LoginRequiredMixin, View):
    def get(self, request):
        kalro_state = kalro_permission_status()
        return render(request, "dashboard/guidance.html", {"kalro_state": kalro_state})


class DataSourcesView(LoginRequiredMixin, View):
    def get(self, request):
        weather_no_notice = no_current_kmd_notice()
        pest_no_notice = no_current_pest_notice()
        synthetic_weather = _latest_synthetic_weather()
        synthetic_pest = _latest_synthetic_pest_notice()
        return render(
            request,
            "dashboard/data_sources.html",
            {
                "weather_no_notice": weather_no_notice,
                "pest_no_notice": pest_no_notice,
                "synthetic_weather": synthetic_weather,
                "synthetic_pest": synthetic_pest,
                "demo_mode": bool(settings.MAJISHAMBA.get("DEMO_MODE", False)) and bool(settings.DEBUG),
            },
        )
