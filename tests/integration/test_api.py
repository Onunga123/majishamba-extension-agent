"""Integration tests for the public REST API (``/api/v1/``).

Covers token authentication (valid / missing / invalid / revoked / expired /
insufficient scope), the per-request eligibility re-check, the
advisory-request and approval endpoints (which share their services with the
server-rendered web views), token introspect / revoke, and the
``generate_api_token`` management command. Two tests exercise the refactored
web views to confirm the service extraction did not change their behaviour.
"""

from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.advisories.models import Advisory, AdvisoryEvidence
from apps.agents.models import AdvisoryRun
from apps.api.models import ApiToken, hash_token
from apps.approvals.models import OfficerApproval
from apps.audit.models import AuditEvent
from tests.factories.models import AdvisoryFactory, FarmerClusterFactory

User = get_user_model()

API_ADVISORY = "/api/v1/advisories/request/"  # back-compat alias of endpoint 3
API_ADVISORY_CANONICAL = "/api/v1/advisories/"  # endpoint 3 roadmap path
API_APPROVAL = "/api/v1/approvals/"
API_INTROSPECT = "/api/v1/token/introspect/"
API_REVOKE = "/api/v1/token/revoke/"
API_RUN_STATUS = "/api/v1/runs/{}/"  # endpoint 4 (format with run_id)
API_ADVISORY_DETAIL = "/api/v1/advisories/{}/"  # endpoint 5 (format with pk)

ALL_SCOPES = [s.value for s in ApiToken.Scope]


def _make_token(user, scopes=None, name="test-token", expires_at=None):
    scopes = scopes if scopes is not None else ALL_SCOPES
    _token, raw = ApiToken.create_token(
        user=user, name=name, scopes=scopes, created_by=user, expires_at=expires_at
    )
    return _token, raw


def _post(client, url, body, raw=None, **extra):
    headers = {}
    if raw:
        headers["HTTP_AUTHORIZATION"] = f"Bearer {raw}"
    headers.update(extra)
    return client.post(url, data=json.dumps(body), content_type="application/json", **headers)


def _get(client, url, raw=None, **extra):
    headers = {}
    if raw:
        headers["HTTP_AUTHORIZATION"] = f"Bearer {raw}"
    headers.update(extra)
    return client.get(url, **headers)


# ---------------------------------------------------------------------------
# Token authentication
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_missing_token_returns_401(client):
    resp = _post(client, API_ADVISORY, {"cluster_id": "KACH-01"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "missing_token"


@pytest.mark.django_db
def test_invalid_token_returns_401(client):
    resp = _post(client, API_ADVISORY, {"cluster_id": "KACH-01"}, raw="majishamba_not-a-real-token")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_token"


@pytest.mark.django_db
def test_x_api_key_header_accepted(client, officer):
    _token, raw = _make_token(officer)
    resp = client.get(API_INTROSPECT, HTTP_X_API_KEY=raw)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_revoked_token_returns_403(client, officer):
    token, raw = _make_token(officer)
    token.revoke()
    resp = _post(client, API_ADVISORY, {"cluster_id": "KACH-01"}, raw=raw)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "token_revoked"


@pytest.mark.django_db
def test_expired_token_returns_403(client, officer):
    _token, raw = _make_token(officer, expires_at=timezone.now() - timedelta(days=1))
    resp = _post(client, API_ADVISORY, {"cluster_id": "KACH-01"}, raw=raw)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "token_expired"


@pytest.mark.django_db
def test_insufficient_scope_returns_403(client, officer):
    # Token can only introspect; requesting an advisory must be refused.
    _token, raw = _make_token(officer, scopes=[ApiToken.Scope.TOKEN_INTROSPECT.value])
    resp = _post(client, API_ADVISORY, {"cluster_id": "KACH-01"}, raw=raw)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "insufficient_scope"


@pytest.mark.django_db
def test_raw_token_is_never_stored_only_its_hash(client, officer):
    _token, raw = _make_token(officer, name="hash-check")
    # The raw token must not appear anywhere in the DB.
    assert not ApiToken.objects.filter(name="hash-check").first().token_hash == raw
    assert ApiToken.objects.filter(token_hash=hash_token(raw)).exists()
    assert ApiToken.objects.filter(token_hash=raw).exists() is False


@pytest.mark.django_db
def test_eligibility_recheck_blocks_demoted_officer(client, officer):
    """A token whose officer is later demoted to viewer is rejected at use time."""
    _token, raw = _make_token(officer)
    officer.role = User.Role.VIEWER
    officer.save()
    resp = _post(client, API_ADVISORY, {"cluster_id": "KACH-01"}, raw=raw)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "not_eligible"


@pytest.mark.django_db
def test_eligibility_recheck_blocks_suspended_officer(client, officer):
    _token, raw = _make_token(officer)
    officer.approval_status = User.ApprovalStatus.SUSPENDED
    officer.save()
    resp = _post(client, API_ADVISORY, {"cluster_id": "KACH-01"}, raw=raw)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "not_eligible"


@pytest.mark.django_db
def test_last_used_at_is_updated_on_use(client, officer):
    token, raw = _make_token(officer)
    assert token.last_used_at is None
    _get(client, API_INTROSPECT, raw=raw)
    token.refresh_from_db()
    assert token.last_used_at is not None


# ---------------------------------------------------------------------------
# Advisory request endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_request_advisory_creates_run(client, officer, monkeypatch):
    # Keep the run in QUEUED so the test is deterministic and does not run the
    # full advisory pipeline.
    monkeypatch.setattr("apps.advisories.services.start_advisory_run_async", lambda pk: None)
    cluster = FarmerClusterFactory(cluster_id="KACH-API-01")
    _token, raw = _make_token(officer)
    resp = _post(client, API_ADVISORY, {"cluster_id": cluster.cluster_id}, raw=raw)
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] is True
    assert body["status"] == "queued"
    assert "run_id" in body


@pytest.mark.django_db
def test_request_advisory_dedup_reuses_run(client, officer, monkeypatch):
    monkeypatch.setattr("apps.advisories.services.start_advisory_run_async", lambda pk: None)
    cluster = FarmerClusterFactory(cluster_id="KACH-API-02")
    _token, raw = _make_token(officer)
    first = _post(client, API_ADVISORY, {"cluster_id": cluster.cluster_id}, raw=raw)
    assert first.status_code == 201
    second = _post(client, API_ADVISORY, {"cluster_id": cluster.cluster_id}, raw=raw)
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["run_id"] == first.json()["run_id"]


@pytest.mark.django_db
def test_request_advisory_cluster_not_found(client, officer):
    _token, raw = _make_token(officer)
    resp = _post(client, API_ADVISORY, {"cluster_id": "DOES-NOT-EXIST"}, raw=raw)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "cluster_not_found"


@pytest.mark.django_db
def test_request_advisory_missing_field(client, officer):
    _token, raw = _make_token(officer)
    resp = _post(client, API_ADVISORY, {}, raw=raw)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "missing_field"


# ---------------------------------------------------------------------------
# Approval endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_record_approval_approves_draft(client, officer):
    advisory = AdvisoryFactory(status=Advisory.Status.DRAFT)
    _token, raw = _make_token(officer)
    resp = _post(
        client,
        API_APPROVAL,
        {
            "advisory_id": advisory.id,
            "decision": OfficerApproval.Decision.APPROVED.value,
            "content_version": advisory.content_version,
        },
        raw=raw,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == Advisory.Status.APPROVED
    advisory.refresh_from_db()
    assert advisory.status == Advisory.Status.APPROVED
    assert OfficerApproval.objects.filter(id=body["approval_id"]).exists()


@pytest.mark.django_db
def test_record_approval_rejects_draft(client, officer):
    advisory = AdvisoryFactory(status=Advisory.Status.DRAFT)
    _token, raw = _make_token(officer)
    resp = _post(
        client,
        API_APPROVAL,
        {
            "advisory_id": advisory.id,
            "decision": OfficerApproval.Decision.REJECTED.value,
            "content_version": advisory.content_version,
            "comments": "Insufficient evidence",
        },
        raw=raw,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == Advisory.Status.REJECTED
    advisory.refresh_from_db()
    assert advisory.status == Advisory.Status.REJECTED


@pytest.mark.django_db
def test_record_approval_version_mismatch(client, officer):
    advisory = AdvisoryFactory(status=Advisory.Status.DRAFT)
    _token, raw = _make_token(officer)
    resp = _post(
        client,
        API_APPROVAL,
        {
            "advisory_id": advisory.id,
            "decision": OfficerApproval.Decision.APPROVED.value,
            "content_version": advisory.content_version + 999,
        },
        raw=raw,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "version_mismatch"


@pytest.mark.django_db
def test_record_approval_not_draft(client, officer):
    advisory = AdvisoryFactory(status=Advisory.Status.APPROVED)
    _token, raw = _make_token(officer)
    resp = _post(
        client,
        API_APPROVAL,
        {
            "advisory_id": advisory.id,
            "decision": OfficerApproval.Decision.APPROVED.value,
            "content_version": advisory.content_version,
        },
        raw=raw,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "not_draft"


@pytest.mark.django_db
def test_record_approval_advisory_not_found(client, officer):
    _token, raw = _make_token(officer)
    resp = _post(
        client,
        API_APPROVAL,
        {
            "advisory_id": 999999,
            "decision": OfficerApproval.Decision.APPROVED.value,
            "content_version": 1,
        },
        raw=raw,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "advisory_not_found"


@pytest.mark.django_db
def test_record_approval_invalid_decision(client, officer):
    advisory = AdvisoryFactory(status=Advisory.Status.DRAFT)
    _token, raw = _make_token(officer)
    resp = _post(
        client,
        API_APPROVAL,
        {
            "advisory_id": advisory.id,
            "decision": "maybe",
            "content_version": advisory.content_version,
        },
        raw=raw,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_decision"


# ---------------------------------------------------------------------------
# Token introspect / revoke
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_token_introspect(client, officer):
    _token, raw = _make_token(officer, name="introspect-test")
    resp = _get(client, API_INTROSPECT, raw=raw)
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"] is True
    assert body["name"] == "introspect-test"
    assert body["user"]["username"] == officer.get_username()
    assert body["user"]["is_officer"] is True
    assert set(body["scopes"]) == set(ALL_SCOPES)


@pytest.mark.django_db
def test_token_revoke(client, officer):
    token, raw = _make_token(officer, name="revoke-test")
    resp = _post(client, API_REVOKE, {}, raw=raw)
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True
    token.refresh_from_db()
    assert token.revoked_at is not None
    # A revoked token can no longer authenticate.
    again = _get(client, API_INTROSPECT, raw=raw)
    assert again.status_code == 403
    assert again.json()["error"]["code"] == "token_revoked"


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_generate_api_token_command(officer):
    out = StringIO()
    call_command(
        "generate_api_token",
        "--user",
        officer.get_username(),
        "--name",
        "cmd-test",
        "--scopes",
        "advisories:request",
        "token:introspect",
        "--days",
        "30",
        stdout=out,
    )
    output = out.getvalue()
    assert "Store this raw token" in output
    raw = [ln for ln in output.splitlines() if ln.strip()][-1]
    assert raw.startswith("majishamba_")
    # Only the hash is persisted; the raw token is not.
    assert ApiToken.objects.filter(token_hash=hash_token(raw)).exists()
    assert ApiToken.objects.filter(token_hash=raw).exists() is False
    token = ApiToken.objects.get(token_hash=hash_token(raw))
    assert token.name == "cmd-test"
    assert "advisories:request" in token.scopes
    assert token.expires_at is not None


@pytest.mark.django_db
def test_generate_api_token_rejects_non_officer(viewer):
    with pytest.raises(CommandError):
        call_command(
            "generate_api_token",
            "--user",
            viewer.get_username(),
            "--name",
            "bad",
            "--scopes",
            "advisories:request",
            stdout=StringIO(),
        )


# ---------------------------------------------------------------------------
# Web views still work after the service extraction
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_web_request_advisory_still_redirects_to_run(officer_client, monkeypatch):
    monkeypatch.setattr("apps.advisories.services.start_advisory_run_async", lambda pk: None)
    cluster = FarmerClusterFactory(cluster_id="KACH-WEB-01")
    resp = officer_client.post("/advisories/request/", {"cluster_id": cluster.cluster_id})
    assert resp.status_code == 302
    assert "/advisories/runs/" in resp.url


@pytest.mark.django_db
def test_web_approval_gate_still_records_approval(officer_client):
    advisory = AdvisoryFactory(status=Advisory.Status.DRAFT)
    resp = officer_client.post(
        f"/approvals/{advisory.id}/",
        {
            "decision": OfficerApproval.Decision.APPROVED.value,
            "comments": "web approval",
            "content_version": advisory.content_version,
        },
    )
    assert resp.status_code == 302


# ---------------------------------------------------------------------------
# Phase 2 — advisory integration: canonical request path (endpoint 3),
# run-status polling (endpoint 4), advisory detail (endpoint 5), and audit
# attribution to the token user.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_request_advisory_canonical_path(client, officer, monkeypatch):
    """Endpoint 3 roadmap path POST /api/v1/advisories/ works like the alias."""
    monkeypatch.setattr("apps.advisories.services.start_advisory_run_async", lambda pk: None)
    cluster = FarmerClusterFactory(cluster_id="KACH-CANON-01")
    _token, raw = _make_token(officer)
    resp = _post(client, API_ADVISORY_CANONICAL, {"cluster_id": cluster.cluster_id}, raw=raw)
    assert resp.status_code == 201
    assert resp.json()["created"] is True
    assert "run_id" in resp.json()


@pytest.mark.django_db
def test_request_advisory_audit_attributes_to_token_user(client, officer, monkeypatch):
    """Roadmap Phase 2 gate: AuditEvent.actor equals the token user."""
    monkeypatch.setattr("apps.advisories.services.start_advisory_run_async", lambda pk: None)
    cluster = FarmerClusterFactory(cluster_id="KACH-AUDIT-01")
    _token, raw = _make_token(officer)
    resp = _post(client, API_ADVISORY, {"cluster_id": cluster.cluster_id}, raw=raw)
    assert resp.status_code == 201
    assert AuditEvent.objects.filter(actor=officer, action="advisory:request").exists()


@pytest.mark.django_db
def test_run_status_polls_to_completed(client, officer, monkeypatch):
    """Endpoint 4: a sync run polls to COMPLETED[_WITH_FALLBACK] with the advisory id."""
    cluster = FarmerClusterFactory(cluster_id="KACH-POLL-01")
    adv = AdvisoryFactory(status=Advisory.Status.DRAFT)
    monkeypatch.setattr(
        "apps.agents.run_worker.run_advisory_pipeline",
        lambda **kw: {
            "advisory_id": adv.id,
            "generation_mode": "fallback_template",
            "request_id": "t-poll",
        },
    )
    _token, raw = _make_token(officer)
    resp = _post(client, API_ADVISORY, {"cluster_id": cluster.cluster_id}, raw=raw)
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]
    status = _get(client, API_RUN_STATUS.format(run_id), raw=raw)
    assert status.status_code == 200
    body = status.json()
    assert body["status"] in (
        AdvisoryRun.Status.COMPLETED,
        AdvisoryRun.Status.COMPLETED_WITH_FALLBACK,
    )
    assert body["result_advisory_id"] == adv.id


@pytest.mark.django_db
def test_run_status_failed_on_pipeline_exception(client, officer, monkeypatch):
    """A pipeline exception records a FAILED run with an error message."""
    cluster = FarmerClusterFactory(cluster_id="KACH-FAIL-01")

    def boom(**kw):
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr("apps.agents.run_worker.run_advisory_pipeline", boom)
    _token, raw = _make_token(officer)
    resp = _post(client, API_ADVISORY, {"cluster_id": cluster.cluster_id}, raw=raw)
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]
    status = _get(client, API_RUN_STATUS.format(run_id), raw=raw)
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == AdvisoryRun.Status.FAILED
    assert "pipeline exploded" in body["error_message"]


@pytest.mark.django_db
def test_run_status_access_rule(client, officer, supervisor, system_admin, viewer):
    """Endpoint 4 access: owner / officer / sysadmin may read; a viewer may not."""
    cluster = FarmerClusterFactory(cluster_id="KACH-ACCESS-01")
    run = AdvisoryRun.objects.create(
        requested_by=officer,
        cluster=cluster,
        status=AdvisoryRun.Status.COMPLETED,
    )
    url = API_RUN_STATUS.format(run.run_id)

    # Owner (the officer who requested the run) → 200.
    _, owner_raw = _make_token(officer)
    assert _get(client, url, raw=owner_raw).status_code == 200
    # Another officer (supervisor) → 200: any officer may view a run.
    _, sup_raw = _make_token(supervisor)
    assert _get(client, url, raw=sup_raw).status_code == 200
    # System admin → 200.
    _, admin_raw = _make_token(system_admin)
    assert _get(client, url, raw=admin_raw).status_code == 200
    # Viewer — fails the scope eligibility check (not officer / sysadmin).
    _, viewer_raw = _make_token(viewer)
    resp = _get(client, url, raw=viewer_raw)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "not_eligible"


@pytest.mark.django_db
def test_run_status_not_found(client, officer):
    _token, raw = _make_token(officer)
    resp = _get(
        client, API_RUN_STATUS.format("00000000-0000-0000-0000-000000000000"), raw=raw
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "run_not_found"


@pytest.mark.django_db
def test_advisory_detail_serializes_evidence_and_version(client, officer):
    """Endpoint 5: detail includes content_version and serialized evidence."""
    advisory = AdvisoryFactory(status=Advisory.Status.DRAFT)
    AdvisoryEvidence.objects.create(
        advisory=advisory,
        source_type="weather",
        source_ref="WeatherSignal#1",
        claim="Onset likely within the planting window.",
        retrieved_at=timezone.now(),
    )
    AdvisoryEvidence.objects.create(
        advisory=advisory,
        source_type="pest",
        source_ref="FallArmyworm#3",
        claim="Low trap counts; continue monitoring.",
    )
    _token, raw = _make_token(officer)
    resp = _get(client, API_ADVISORY_DETAIL.format(advisory.id), raw=raw)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == advisory.id
    assert body["content_version"] == advisory.content_version
    assert body["status"] == Advisory.Status.DRAFT
    assert len(body["evidence"]) == 2
    assert {e["source_type"] for e in body["evidence"]} == {"weather", "pest"}
    assert all("claim" in e and "source_ref" in e for e in body["evidence"])


@pytest.mark.django_db
def test_advisory_detail_hides_soft_deleted(client, officer):
    advisory = AdvisoryFactory(status=Advisory.Status.DRAFT)
    advisory.soft_delete(by_user=officer, reason="test")
    _token, raw = _make_token(officer)
    resp = _get(client, API_ADVISORY_DETAIL.format(advisory.id), raw=raw)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "advisory_not_found"


@pytest.mark.django_db
def test_advisory_detail_not_found(client, officer):
    _token, raw = _make_token(officer)
    resp = _get(client, API_ADVISORY_DETAIL.format(999999), raw=raw)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "advisory_not_found"
