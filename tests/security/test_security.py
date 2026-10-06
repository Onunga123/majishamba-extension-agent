"""Security and governance tests."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.approvals.models import OfficerApproval
from apps.tasks.models import FollowUpTask
from apps.tasks.service import create_follow_up_task_after_approval
from apps.advisories.models import Advisory


@pytest.mark.django_db
def test_viewer_cannot_approve(viewer_client):
    """A viewer must not be able to call the approval gate."""
    from tests.factories.models import AdvisoryFactory
    adv = AdvisoryFactory(cluster__cluster_id="KACH-01", status=Advisory.Status.DRAFT)
    resp = viewer_client.post(f"/approvals/{adv.id}/", {"decision": "approved"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_anonymous_cannot_request_advisory(anonymous_client):
    resp = anonymous_client.get("/advisories/request/")
    assert resp.status_code in {301, 302}


@pytest.mark.django_db
def test_viewer_cannot_request_advisory(viewer_client):
    resp = viewer_client.get("/advisories/request/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_viewer_cannot_open_agent_graph(viewer_client):
    resp = viewer_client.get("/agents/graph/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_no_external_message_can_be_sent_by_agent():
    """A defensive test: the agent module must NOT import any SMS/email/HTTP-send helper."""
    import apps.agents.graph as graph
    import inspect
    src = inspect.getsource(graph)
    forbidden = ["send_sms", "twilio", "africastalking", "send_mail", "requests.post"]
    for term in forbidden:
        assert term not in src, f"agent graph must not contain '{term}'"


@pytest.mark.django_db
def test_follow_up_task_service_enforces_approval_gate(officer):
    from tests.factories.models import AdvisoryFactory
    adv = AdvisoryFactory(cluster__cluster_id="KACH-01", status=Advisory.Status.DRAFT)
    # No approval record yet — must fail.
    res = create_follow_up_task_after_approval(
        approved_advisory_id=adv.id, officer_id=officer.id,
        task_type="field_visit", ward="Kachieng", actor=officer,
    )
    assert "error" in res
    # Add approval — must succeed.
    OfficerApproval.objects.create(advisory=adv, officer=officer, decision=OfficerApproval.Decision.APPROVED)
    adv.status = Advisory.Status.APPROVED
    adv.save()
    res2 = create_follow_up_task_after_approval(
        approved_advisory_id=adv.id, officer_id=officer.id,
        task_type="field_visit", ward="Kachieng", actor=officer,
    )
    assert "task_id" in res2
    assert FollowUpTask.objects.filter(id=res2["task_id"]).exists()


@pytest.mark.django_db
def test_audit_event_written_for_every_tool_call(officer):
    from apps.mcp_tools.tools import get_cluster_plot_history
    from apps.audit.models import AuditEvent
    from tests.factories.models import (
        CountyFactory, SubCountyFactory, WardFactory, FarmerClusterFactory, HouseholdFactory, PlotFactory,
    )
    county = CountyFactory()
    sub = SubCountyFactory(county=county)
    ward = WardFactory(sub_county=sub)
    cluster = FarmerClusterFactory(cluster_id="KACH-99", ward=ward)
    hh = HouseholdFactory(cluster=cluster, household_id="KACH-99-HH-001")
    PlotFactory(household=hh)
    before = AuditEvent.objects.count()
    get_cluster_plot_history(cluster_id="KACH-99")
    after = AuditEvent.objects.count()
    assert after >= before + 1


@pytest.mark.django_db
def test_csrf_protection_on_post():
    """Approvals POST without CSRF token must be rejected."""
    from tests.factories.models import AdvisoryFactory
    adv = AdvisoryFactory(cluster__cluster_id="KACH-01", status=Advisory.Status.DRAFT)
    c = Client(enforce_csrf_checks=True)
    resp = c.post(f"/approvals/{adv.id}/", {"decision": "approved"})
    assert resp.status_code in {403, 302}
