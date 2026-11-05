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

from apps.advisories.models import Advisory
from apps.api.models import ApiToken, hash_token
from apps.approvals.models import OfficerApproval
from tests.factories.models import AdvisoryFactory, FarmerClusterFactory

User = get_user_model()

API_ADVISORY = "/api/v1/advisories/request/"
API_APPROVAL = "/api/v1/approvals/"
API_INTROSPECT = "/api/v1/token/introspect/"
API_REVOKE = "/api/v1/token/revoke/"

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
    advisory.refresh_from_db()
    assert advisory.status == Advisory.Status.APPROVED
