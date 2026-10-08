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

    Humanises internal action codes (including the http:METHOD:path pattern
    emitted by AuditMiddleware) so the activity feed reads as natural language
    (e.g. 'Christopher completed Task #1 — Oct 8, 2026 · 09:46'), not raw
    API/HTTP text. Raw action codes are preserved in `raw_action` for the
    staff-only technical/audit view (progressive disclosure).
    """
    # Map internal action codes to human-readable text.
    action_map = {
        "account:register": "registered an account",
        "account:login": "signed in",
        "account:approve": "approved an account",
        "account:reject": "rejected an account",
        "officer_approval": "reviewed an advisory",
        "advisory:request": "requested an advisory",
        "advisory:approve": "approved an advisory",
        "advisory:reject": "rejected an advisory",
        "advisory:soft_delete": "deleted an advisory",
        "advisory:restore": "restored an advisory",
        "advisory:edit": "edited an advisory",
        "task:complete": "completed a task",
        "task:verify": "verified a task",
        "task:finding": "submitted field findings",
        "create_follow_up_task": "created a follow-up task",
        "agent_run:start": "started an advisory draft",
        "agent_run:end": "finished an advisory draft",
        "agent_run:failure": "failed to draft an advisory",
        "ingest:open_meteo_forecast": "ingested an Open-Meteo forecast",
        "ingest:kmd_bulletin": "ingested a KMD bulletin",
        "ingest:officer_pest_report": "submitted a pest field report",
        "ingest:published_pest_notice": "ingested a published pest notice",
        "ingest:kalro_bibliographic": "recorded KALRO bibliographic info",
        "ingest:kalro_factsheet": "ingested a KALRO factsheet",
    }

    action = event.action
    action_human = action_map.get(action)

    # Humanise http:METHOD:/path/ patterns emitted by AuditMiddleware.
    # Example: 'http:POST:/tasks/1/complete/' → 'completed Task #1'
    if action_human is None and action.startswith("http:"):
        action_human, http_object_label = _humanize_http_action(action)
        if http_object_label:
            obj_label = http_object_label
        else:
            obj_label = ""
    else:
        if action_human is None:
            # Unknown action — keep the raw code as last resort, but mark it
            # clearly so staff can investigate. Non-staff never see the raw
            # code in the activity feed (it's filtered out by the template).
            action_human = action
        # Object label from metadata
        obj_label = ""
        if event.target_type:
            obj_label = f"{event.target_type}"
            if event.target_id:
                obj_label = f"{event.target_type} #{event.target_id}"
        elif event.metadata and "advisory_id" in event.metadata:
            obj_label = f"Advisory #{event.metadata['advisory_id']}"
        elif event.metadata and "username" in event.metadata:
            obj_label = f"account '{event.metadata['username']}'"
        elif event.metadata and "cluster_id" in event.metadata:
            obj_label = f"cluster {event.metadata['cluster_id']}"

    # Result badge: derive from action
    result_badge = ""
    if "approve" in action and "account" not in action:
        result_badge = "approved"
    elif "reject" in action and "account" not in action:
        result_badge = "rejected"
    elif "delete" in action or "soft_delete" in action:
        result_badge = "deleted"
    elif "restore" in action:
        result_badge = "restored"
    elif "complete" in action:
        result_badge = "completed"
    elif "verify" in action:
        result_badge = "verified"
    elif "login" in action:
        result_badge = "session started"
    elif "register" in action:
        result_badge = "pending review"
    elif "edit" in action:
        result_badge = "edited"
    elif "ingest" in action or "recorded" in action_human:
        result_badge = "ingested"
    elif "created" in action_human:
        result_badge = "created"
    elif "started" in action_human:
        result_badge = "started"
    elif "finished" in action_human:
        result_badge = "finished"
    elif "failed" in action_human:
        result_badge = "failed"

    actor_name = event.actor.get_username() if event.actor else "system"
    return {
        "actor": event.actor,
        "actor_name": actor_name,
        "action_human": action_human,
        "object_label": obj_label,
        "when_display": event.created_at,
        "when_iso": event.created_at.isoformat() if event.created_at else "",
        "result_badge": result_badge,
        "raw_action": action,  # kept for staff-only technical view
    }


def _humanize_http_action(action: str) -> tuple[str, str]:
    """Convert an 'http:METHOD:/path/...' audit action into a human-readable
    phrase plus an object label.

    Examples:
        'http:POST:/tasks/1/complete/'      → ('completed', 'Task #1')
        'http:POST:/advisories/12/restore/' → ('restored', 'Advisory #12')
        'http:POST:/advisories/12/delete/'   → ('deleted', 'Advisory #12')
        'http:POST:/approvals/30/'          → ('reviewed', 'Advisory #30')
        'http:POST:/tasks/4/findings/'       → ('submitted field findings for', 'Task #4')
        'http:POST:/tasks/4/verify/'        → ('verified', 'Task #4')
        'http:POST:/advisories/request/'    → ('requested', 'an advisory')
        'http:POST:/accounts/register/'    → ('registered', 'an account')
        'http:POST:/accounts/login/'        → ('signed in', '')
        'http:POST:/accounts/logout/'       → ('signed out', '')

    Returns (action_human, object_label). For unmatched patterns, returns
    ('performed an action', '') so the activity feed always reads cleanly.
    """
    import re

    # Strip the 'http:METHOD:' prefix to get the path
    m = re.match(r"http:(\w+):(.*)", action)
    if not m:
        return ("performed an action", "")
    method, path = m.group(1), m.group(2)

    # Pattern: /advisories/<id>/restore/
    m = re.match(r"/advisories/(\d+)/restore/?$", path)
    if m:
        return ("restored", f"Advisory #{m.group(1)}")
    # Pattern: /advisories/<id>/delete/
    m = re.match(r"/advisories/(\d+)/delete/?$", path)
    if m:
        return ("deleted", f"Advisory #{m.group(1)}")
    # Pattern: /advisories/<id>/edit/
    m = re.match(r"/advisories/(\d+)/edit/?$", path)
    if m:
        return ("edited", f"Advisory #{m.group(1)}")
    # Pattern: /advisories/request/
    m = re.match(r"/advisories/request/?$", path)
    if m:
        return ("requested", "an advisory")
    # Pattern: /approvals/<id>/ (POST = approve/reject/defer)
    m = re.match(r"/approvals/(\d+)/?$", path)
    if m:
        return ("reviewed", f"Advisory #{m.group(1)}")
    # Pattern: /tasks/<id>/complete/
    m = re.match(r"/tasks/(\d+)/complete/?$", path)
    if m:
        return ("completed", f"Task #{m.group(1)}")
    # Pattern: /tasks/<id>/verify/
    m = re.match(r"/tasks/(\d+)/verify/?$", path)
    if m:
        return ("verified", f"Task #{m.group(1)}")
    # Pattern: /tasks/<id>/findings/
    m = re.match(r"/tasks/(\d+)/findings/?$", path)
    if m:
        return ("submitted field findings for", f"Task #{m.group(1)}")
    # Pattern: /accounts/login/ /accounts/logout/ /accounts/register/
    if "/accounts/login" in path:
        return ("signed in", "")
    if "/accounts/logout" in path:
        return ("signed out", "")
    if "/accounts/register" in path:
        return ("registered", "an account")
    if "/accounts/review" in path and method == "POST":
        return ("reviewed an account", "")

    # Fallback: 'performed POST on /path/' — better than the raw string but
    # clearly indicates we couldn't map it. Staff can still see the raw action.
    return ("performed an action on", path)


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


def _cluster_contextual_action(cluster_stats: dict, can_request_advisory: bool, can_approve: bool) -> dict:
    """Return the primary + secondary actions for a cluster row, based on its state.

    Per the HCI spec: do not show identical actions for every cluster.
    The primary action depends on the cluster's latest advisory state:

        draft          → 'Review' (links to advisory detail / approval gate)
        approved + open task → 'Field visit' (links to task)
        approved (no open task) → 'View' (no primary action needed)
        no_advisory    → 'Request' (officers only)
        rejected/deferred/needs_evidence → 'View' (officer decides)

    Returns a dict: {
        'primary_label': str, 'primary_url': str, 'primary_aria': str,
        'secondary': list[dict],  # for the ⋮ menu
    }
    """
    cluster = cluster_stats["cluster"]
    latest_status = cluster_stats["latest_advisory_status"]
    next_action = cluster_stats["next_action"]
    cluster_id = cluster.cluster_id

    secondary: list[dict] = [
        {"label": "Open cluster page", "url": f"/clusters/{cluster_id}/"},
        {"label": "View advisories", "url": f"/advisories/?cluster={cluster_id}"},
        {"label": "View tasks", "url": "/tasks/"},
    ]

    # Default: no primary action, just 'View'
    primary = {
        "primary_label": "View",
        "primary_url": f"/clusters/{cluster_id}/",
        "primary_aria": f"View cluster {cluster_id}",
    }

    if latest_status is None:
        # No advisory yet → Request (officers only)
        if can_request_advisory:
            primary = {
                "primary_label": "Request",
                "primary_url": f"/advisories/request/?cluster={cluster_id}",
                "primary_aria": f"Request advisory for {cluster_id}",
            }
            secondary.insert(0, {
                "label": "Request advisory",
                "url": f"/advisories/request/?cluster={cluster_id}",
            })
    elif latest_status == Advisory.Status.DRAFT:
        # Draft → Review (approvers go to approval gate, others to detail)
        if can_approve:
            # Find the latest draft advisory id for this cluster (best effort)
            latest_draft = cluster.advisories.filter(status=Advisory.Status.DRAFT).order_by("-created_at").first()
            if latest_draft:
                primary = {
                    "primary_label": "Review",
                    "primary_url": f"/approvals/{latest_draft.id}/",
                    "primary_aria": f"Review draft advisory #{latest_draft.id} for {cluster_id}",
                }
        else:
            latest_draft = cluster.advisories.filter(status=Advisory.Status.DRAFT).order_by("-created_at").first()
            if latest_draft:
                primary = {
                    "primary_label": "Review",
                    "primary_url": f"/advisories/{latest_draft.id}/",
                    "primary_aria": f"Open draft advisory #{latest_draft.id} for {cluster_id}",
                }
    elif latest_status == Advisory.Status.APPROVED and next_action == "Field visit":
        # Approved with open follow-up task → Field visit (link to the task)
        latest_approved = cluster.advisories.filter(status=Advisory.Status.APPROVED).order_by("-created_at").first()
        if latest_approved:
            open_task = latest_approved.follow_up_tasks.exclude(
                status__in=[FollowUpTask.Status.COMPLETED, FollowUpTask.Status.VERIFIED,
                            FollowUpTask.Status.CLOSED, FollowUpTask.Status.CANCELLED]
            ).order_by("deadline").first()
            if open_task:
                primary = {
                    "primary_label": "Field visit",
                    "primary_url": f"/tasks/{open_task.id}/",
                    "primary_aria": f"Open field-visit task #{open_task.id} for {cluster_id}",
                }
    elif latest_status == Advisory.Status.NEEDS_EVIDENCE:
        latest_adv = cluster.advisories.order_by("-created_at").first()
        if latest_adv:
            primary = {
                "primary_label": "View",
                "primary_url": f"/advisories/{latest_adv.id}/",
                "primary_aria": f"Open advisory #{latest_adv.id} for {cluster_id}",
            }
    # For approved (no open task) / rejected / deferred: keep default 'View'

    return {**primary, "secondary": secondary}


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

        # Compute the contextual primary action per cluster (HCI: do not show
        # identical actions for every cluster — primary action depends on state).
        for cs in filtered_cluster_stats:
            cs["contextual_action"] = _cluster_contextual_action(
                cs, can_request_advisory=can_request_advisory, can_approve=can_approve,
            )

        # --- Needs Your Attention ---
        # Per HCI spec: only items that actually require attention belong here.
        # Three categories only: drafts awaiting review, field visits required,
        # pending tasks. 'Recently approved' was removed — it's history, not
        # attention (it lives in the 'Recent advisories → Approved' group).
        drafts_awaiting_review_count = Advisory.objects.filter(status=Advisory.Status.DRAFT).count()
        field_visit_advisories_count = Advisory.objects.filter(
            status=Advisory.Status.APPROVED,
            follow_up_tasks__status__in=[
                FollowUpTask.Status.ASSIGNED,
                FollowUpTask.Status.IN_PROGRESS,
            ],
        ).distinct().count()
        pending_tasks_count = FollowUpTask.objects.exclude(
            status__in=[FollowUpTask.Status.COMPLETED, FollowUpTask.Status.VERIFIED,
                         FollowUpTask.Status.CLOSED, FollowUpTask.Status.CANCELLED]
        ).count()

        needs_attention = {
            # Counts only — the actual records live in the 'Recent advisories'
            # and 'Tasks' sections to avoid duplicate information on the page.
            "drafts_count": drafts_awaiting_review_count,
            "field_visits_count": field_visit_advisories_count,
            "pending_tasks_count": pending_tasks_count,
            # Summary lines (one each) — used in the attention card body
            "drafts_summary": f"{drafts_awaiting_review_count} draft{'s' if drafts_awaiting_review_count != 1 else ''} awaiting review",
            "field_visits_summary": f"{field_visit_advisories_count} approved advisories awaiting field verification",
            "pending_tasks_summary": f"{pending_tasks_count} pending task{'s' if pending_tasks_count != 1 else ''}",
        }

        # --- Recent advisories grouped by workflow status ---
        # Per HCI spec: group by meaningful workflow status.
        # Three groups: Draft (AI-generated, needs human review),
        # Field verification (approved, awaiting field visit), Approved (no open task).
        # Rejected advisories are not promoted to a top-level group on the dashboard
        # (officers can see them in the full /advisories/ list) — but if any exist
        # we surface them as a compact "Rejected" group so the officer knows.
        recent_advisories_qs = Advisory.objects.select_related("cluster").order_by("-created_at")
        approved_with_open_task = recent_advisories_qs.filter(
            status=Advisory.Status.APPROVED,
            follow_up_tasks__status__in=[
                FollowUpTask.Status.ASSIGNED,
                FollowUpTask.Status.IN_PROGRESS,
            ],
        ).distinct()[:7]
        approved_without_open_task = recent_advisories_qs.filter(
            status=Advisory.Status.APPROVED,
        ).exclude(
            follow_up_tasks__status__in=[
                FollowUpTask.Status.ASSIGNED,
                FollowUpTask.Status.IN_PROGRESS,
            ],
        ).distinct()[:7]
        advisories_by_status = {
            "draft": list(recent_advisories_qs.filter(status=Advisory.Status.DRAFT)[:7]),
            "field_verification": list(approved_with_open_task),
            "approved": list(approved_without_open_task),
            "rejected": list(recent_advisories_qs.filter(status=Advisory.Status.REJECTED)[:5]),
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
