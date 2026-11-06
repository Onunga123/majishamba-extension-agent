"""End-to-end acceptance test for the Phase 3 Base44 Superagent flow.

Exercises the full advisory-generation flow a Base44 client drives, against the
Django test client in synchronous run mode (``MAJISHAMBA_SYNC_RUN=1``), to prove
the ``/api/v1/`` API supports the roadmap's Phase 3 acceptance criteria
(roadmap §11, Phase 3):

  GET /api/v1/health/            -> 200 (no auth)
  GET /api/v1/clusters/          -> 200 (any active token)
  POST /api/v1/advisories/       -> 201 {run_id, status, created}
  GET  /api/v1/runs/<uuid>/      -> poll to COMPLETED[_WITH_FALLBACK]
  GET  /api/v1/advisories/<pk>/  -> 200 draft + evidence

This is the API-side validation of Phase 3. The Base44 Superagent app itself is
built outside this repo (roadmap §11, Phase 3: "Base44 project (outside this
repo); Render dashboard; no Kachieng' repository changes beyond environment").
"""

from __future__ import annotations

import json

import pytest
from django.utils import timezone

from apps.advisories.models import Advisory, AdvisoryEvidence
from apps.agents.models import AdvisoryRun
from apps.api.models import ApiToken
from tests.factories.models import AdvisoryFactory, FarmerClusterFactory

ALL_SCOPES = [s.value for s in ApiToken.Scope]


def _make_token(user, scopes=None, name="phase3-token"):
    scopes = scopes if scopes is not None else ALL_SCOPES
    _token, raw = ApiToken.create_token(
        user=user, name=name, scopes=scopes, created_by=user
    )
    return _token, raw


def _bearer(raw):
    return {"HTTP_AUTHORIZATION": f"Bearer {raw}"}


@pytest.mark.django_db
def test_phase3_superagent_flow_health_clusters_request_poll_display(
    client, officer, monkeypatch
):
    """The full Base44 Superagent flow against /api/v1/ (sync mode).

    browse clusters -> request an advisory -> poll to completion -> display the
    draft with evidence. This is the Phase 3 acceptance criterion, exercised
    from the API side.
    """
    # --- 1. Health (no auth) ---
    health = client.get("/api/v1/health/")
    assert health.status_code == 200
    assert health.json()["status"] in ("ok", "degraded")

    # An officer token drives the rest of the flow.
    _token, raw = _make_token(officer, name="phase3-officer")

    # --- 2. Browse clusters ---
    cluster_a = FarmerClusterFactory(cluster_id="KACH-P3-01", name="Sori", locality="Sori")
    FarmerClusterFactory(cluster_id="KACH-P3-02", name="Kiranda", locality="Kiranda")
    clusters = client.get("/api/v1/clusters/", **_bearer(raw))
    assert clusters.status_code == 200
    cbody = clusters.json()
    assert cbody["count"] >= 2
    ids = {c["cluster_id"] for c in cbody["results"]}
    assert {"KACH-P3-01", "KACH-P3-02"} <= ids

    # --- 3. Submit an advisory request for the chosen cluster ---
    # The advisory the (monkeypatched) pipeline will return. It belongs to the
    # requested cluster so the detail endpoint reports the right cluster_id.
    adv = AdvisoryFactory(status=Advisory.Status.DRAFT, cluster=cluster_a)
    AdvisoryEvidence.objects.create(
        advisory=adv,
        source_type="weather",
        source_ref="WeatherSignal#P3",
        claim="Onset likely within the planting window.",
        retrieved_at=timezone.now(),
    )
    monkeypatch.setattr(
        "apps.agents.run_worker.run_advisory_pipeline",
        lambda **kw: {
            "advisory_id": adv.id,
            "generation_mode": "fallback_template",
            "request_id": "phase3-e2e",
        },
    )
    request = client.post(
        "/api/v1/advisories/",
        data=json.dumps({"cluster_id": "KACH-P3-01"}),
        content_type="application/json",
        **_bearer(raw),
    )
    assert request.status_code == 201
    rbody = request.json()
    assert rbody["created"] is True
    assert rbody["status"] == AdvisoryRun.Status.QUEUED or "run_id" in rbody
    run_id = rbody["run_id"]

    # --- 4. Poll run status until terminal (sync run completes within the request) ---
    status = client.get(f"/api/v1/runs/{run_id}/", **_bearer(raw))
    assert status.status_code == 200
    sbody = status.json()
    assert sbody["status"] in (
        AdvisoryRun.Status.COMPLETED,
        AdvisoryRun.Status.COMPLETED_WITH_FALLBACK,
    )
    advisory_id = sbody["result_advisory_id"]
    assert advisory_id == adv.id

    # --- 5. Fetch the advisory draft + evidence ---
    detail = client.get(f"/api/v1/advisories/{advisory_id}/", **_bearer(raw))
    assert detail.status_code == 200
    dbody = detail.json()
    assert dbody["id"] == advisory_id
    assert dbody["status"] == Advisory.Status.DRAFT
    assert dbody["cluster_id"] == "KACH-P3-01"
    assert dbody["content_version"] == adv.content_version
    assert len(dbody["evidence"]) >= 1
    assert dbody["evidence"][0]["source_type"] == "weather"
    assert dbody["evidence"][0]["claim"] == "Onset likely within the planting window."


@pytest.mark.django_db
def test_phase3_flow_second_human_supervisor_configurable(
    client, officer, supervisor, monkeypatch
):
    """Phase 3 acceptance: 'a second human (supervisor) is configurable.'

    A supervisor (a second officer who can approve) authenticates with their own
    token and can read the same run + advisory the requesting officer produced.
    The run-status access rule (owner / any officer / sysadmin) lets the
    supervisor in; the requesting officer remains the run owner.
    """
    cluster = FarmerClusterFactory(cluster_id="KACH-P3-SUP-01")
    adv = AdvisoryFactory(status=Advisory.Status.DRAFT, cluster=cluster)
    monkeypatch.setattr(
        "apps.agents.run_worker.run_advisory_pipeline",
        lambda **kw: {
            "advisory_id": adv.id,
            "generation_mode": "fallback_template",
            "request_id": "phase3-sup",
        },
    )

    # The officer requests the run (they become the run owner).
    _off_token, off_raw = _make_token(officer, name="phase3-officer-2")
    request = client.post(
        "/api/v1/advisories/",
        data=json.dumps({"cluster_id": "KACH-P3-SUP-01"}),
        content_type="application/json",
        **_bearer(off_raw),
    )
    assert request.status_code == 201
    run_id = request.json()["run_id"]

    # A second human (supervisor), with their own token, polls the run and reads
    # the advisory. The access rule admits any officer.
    _sup_token, sup_raw = _make_token(supervisor, name="phase3-supervisor")
    status = client.get(f"/api/v1/runs/{run_id}/", **_bearer(sup_raw))
    assert status.status_code == 200
    assert status.json()["status"] in (
        AdvisoryRun.Status.COMPLETED,
        AdvisoryRun.Status.COMPLETED_WITH_FALLBACK,
    )
    advisory_id = status.json()["result_advisory_id"]

    detail = client.get(f"/api/v1/advisories/{advisory_id}/", **_bearer(sup_raw))
    assert detail.status_code == 200
    assert detail.json()["id"] == advisory_id
