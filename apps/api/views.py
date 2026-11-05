"""Public REST API views for external integrations (e.g. a Base44-built app).

All views authenticate via the ``token_required`` decorator (Bearer token),
are CSRF-exempt, and return JSON. They wrap the same domain services used by
the server-rendered web views, so behaviour stays consistent across channels.
"""

from __future__ import annotations

import json
import logging

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.advisories.models import Advisory
from apps.advisories.services import (
    ClusterNotFound,
    request_advisory_run,
)
from apps.agents.models import AdvisoryRun
from apps.approvals.models import OfficerApproval
from apps.approvals.services import (
    AdvisoryNotDraft,
    AdvisoryNotFound,
    VersionMismatch,
    record_approval,
)
from apps.audit.service import log_audit_event

from .auth import token_required
from .models import ApiToken

logger = logging.getLogger("majishamba.api")


def _json_error(status: int, code: str, message: str, **extra) -> JsonResponse:
    payload = {"error": {"code": code, "message": message}}
    payload["error"].update(extra)
    return JsonResponse(payload, status=status)


def _read_json(request: HttpRequest):
    try:
        return json.loads(request.body or b"{}"), None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, _json_error(400, "bad_json", "Request body must be valid JSON.")


@require_http_methods(["POST"])
@token_required(ApiToken.Scope.ADVISORIES_REQUEST)
def request_advisory_view(request: HttpRequest) -> JsonResponse:
    """Request a draft advisory run for a cluster.

    Body: ``{"cluster_id": "<FarmerCluster.cluster_id>"}``
    Returns ``{"run_id", "status", "created"}`` (201 if a new run was created,
    200 if a recent in-flight run was reused).
    """
    body, err = _read_json(request)
    if err:
        return err
    cluster_id = body.get("cluster_id")
    if not cluster_id:
        return _json_error(400, "missing_field", "Field 'cluster_id' is required.")
    try:
        result = request_advisory_run(actor=request.user, cluster_id=str(cluster_id))
    except PermissionDenied:
        return _json_error(
            403, "not_eligible", "The account bound to this token cannot request advisories."
        )
    except ClusterNotFound:
        return _json_error(404, "cluster_not_found", f"No cluster with cluster_id '{cluster_id}'.")
    # Attribute the request to the token user so the API path is auditable
    # (roadmap Phase 2 gate: AuditEvent.actor equals the token user).
    log_audit_event(
        actor=request.user,
        action="advisory:request",
        target=None,
        metadata={
            "cluster_id": str(cluster_id),
            "run_id": result.run_id,
            "created": result.created,
        },
    )
    return JsonResponse(
        {"run_id": result.run_id, "status": result.status, "created": result.created},
        status=201 if result.created else 200,
    )


@require_http_methods(["POST"])
@token_required(ApiToken.Scope.APPROVALS_RECORD)
def record_approval_view(request: HttpRequest) -> JsonResponse:
    """Record an officer's approval decision on a DRAFT advisory.

    Body: ``{"advisory_id", "decision", "content_version", "comments"?, "create_followup"?, "task_type"?, "deadline"?}``
    Returns ``{"advisory_id", "status", "approval_id", "followup_task_id"}``.
    """
    body, err = _read_json(request)
    if err:
        return err
    advisory_id = body.get("advisory_id")
    decision = body.get("decision")
    content_version = body.get("content_version")
    if advisory_id is None or not decision or content_version is None:
        return _json_error(
            400,
            "missing_field",
            "Fields 'advisory_id', 'decision', 'content_version' are required.",
        )
    valid_decisions = {d.value for d in OfficerApproval.Decision}
    if decision not in valid_decisions:
        return _json_error(
            400,
            "invalid_decision",
            f"'decision' must be one of {sorted(valid_decisions)}.",
        )
    try:
        content_version = int(content_version)
        advisory_pk = int(advisory_id)
    except (TypeError, ValueError):
        return _json_error(
            400, "invalid_field", "'advisory_id' and 'content_version' must be integers."
        )

    try:
        result = record_approval(
            actor=request.user,
            advisory_pk=advisory_pk,
            decision=decision,
            comments=str(body.get("comments", "") or ""),
            content_version=content_version,
            create_followup=bool(body.get("create_followup")),
            task_type=str(body.get("task_type") or "field_visit"),
            deadline=body.get("deadline"),
        )
    except PermissionDenied:
        return _json_error(
            403, "not_eligible", "The account bound to this token cannot record approvals."
        )
    except AdvisoryNotFound:
        return _json_error(404, "advisory_not_found", f"No advisory with id {advisory_id}.")
    except AdvisoryNotDraft:
        return _json_error(409, "not_draft", "Advisory is no longer in DRAFT status.")
    except VersionMismatch:
        return _json_error(
            409,
            "version_mismatch",
            "Advisory was updated; review the latest version before deciding.",
        )

    return JsonResponse(
        {
            "advisory_id": result.advisory_id,
            "status": result.status,
            "approval_id": result.approval_id,
            "followup_task_id": result.followup_task_id,
        },
        status=201,
    )


@require_http_methods(["GET"])
@token_required(ApiToken.Scope.TOKEN_INTROSPECT)
def token_introspect_view(request: HttpRequest) -> JsonResponse:
    """Return the metadata of the token making the request."""
    token = request.api_token
    user = request.user
    return JsonResponse(
        {
            "active": True,
            "name": token.name,
            "scopes": token.scopes,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
            "last_used_at": token.last_used_at.isoformat() if token.last_used_at else None,
            "created_at": token.created_at.isoformat(),
            "user": {
                "id": user.id,
                "username": user.get_username(),
                "role": user.role,
                "is_officer": user.is_officer(),
                "can_approve": user.can_approve(),
            },
        }
    )


@require_http_methods(["POST"])
@token_required(ApiToken.Scope.TOKEN_REVOKE)
def token_revoke_view(request: HttpRequest) -> JsonResponse:
    """Revoke the token making the request."""
    token = request.api_token
    token.revoke()
    log_audit_event(
        actor=request.user,
        action="api_token:revoke",
        target=token,
        metadata={"name": token.name},
    )
    return JsonResponse({"revoked": True, "name": token.name})


@require_http_methods(["GET"])
@token_required(ApiToken.Scope.ADVISORIES_READ)
def run_status_view(request: HttpRequest, run_id) -> JsonResponse:
    """Return the status of an advisory run (endpoint 4: GET /runs/<uuid>/).

    A Base44 client polls this after ``POST /advisories/`` until ``status``
    reaches ``completed`` / ``completed_with_fallback`` (then fetches the
    draft via ``GET /advisories/<pk>/`` using ``result_advisory_id``) or
    ``failed`` (with ``error_message``). Access mirrors the web
    ``AdvisoryRunStatusView``: the run owner, any officer, or a system admin.
    """
    run = (
        AdvisoryRun.objects.select_related("cluster", "result_advisory")
        .filter(run_id=run_id)
        .first()
    )
    if run is None:
        return _json_error(404, "run_not_found", f"No run with run_id '{run_id}'.")
    user = request.user
    if (
        run.requested_by_id != user.id
        and not user.is_officer()
        and not user.is_system_admin()
    ):
        return _json_error(403, "not_eligible", "You cannot view this run.")
    return JsonResponse(
        {
            "run_id": str(run.run_id),
            "status": run.status,
            "cluster_id": run.cluster.cluster_id,
            "current_message": run.current_message,
            "created_at": run.created_at.isoformat(),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "result_advisory_id": run.result_advisory_id,
            "error_message": run.error_message,
            "generation_mode": run.generation_mode,
        }
    )


@require_http_methods(["GET"])
@token_required(ApiToken.Scope.ADVISORIES_READ)
def advisory_detail_view(request: HttpRequest, advisory_pk: int) -> JsonResponse:
    """Return an advisory draft and its evidence (endpoint 5: GET /advisories/<pk>/).

    Soft-deleted advisories are hidden (404) — the default manager excludes
    them. Access mirrors the web ``AdvisoryDetailView``: any officer or system
    admin with the ``advisories:read`` scope.
    """
    advisory = (
        Advisory.objects.select_related("cluster", "created_by")
        .filter(pk=advisory_pk)
        .first()
    )
    if advisory is None:
        return _json_error(404, "advisory_not_found", f"No advisory with id {advisory_pk}.")
    evidence = [
        {
            "source_type": e.source_type,
            "source_ref": e.source_ref,
            "claim": e.claim,
            "is_stale": e.is_stale,
            "retrieved_at": e.retrieved_at.isoformat() if e.retrieved_at else None,
            "source_observed_at": e.source_observed_at,
            "source_url": e.source_url,
        }
        for e in advisory.evidence.all()
    ]
    return JsonResponse(
        {
            "id": advisory.id,
            "status": advisory.status,
            "cluster_id": advisory.cluster.cluster_id,
            "recommendation_type": advisory.recommendation_type,
            "summary": advisory.summary,
            "body": advisory.body,
            "confidence": advisory.confidence,
            "limitations": advisory.limitations,
            "content_version": advisory.content_version,
            "evidence": evidence,
            "crop": advisory.crop,
            "season": advisory.season,
            "county": advisory.county,
            "sub_county": advisory.sub_county,
            "ward": advisory.ward,
            "model_name": advisory.model_name,
            "generation_mode": advisory.generation_mode,
            "created_at": advisory.created_at.isoformat(),
            "updated_at": advisory.updated_at.isoformat(),
        }
    )
