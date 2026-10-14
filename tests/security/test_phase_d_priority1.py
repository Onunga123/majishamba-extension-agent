"""Phase D Priority 1 regression tests — authorization and identity integrity.

Covers the approved Priority 1 findings:

D-01: ``is_staff`` is no longer used as an authorization gate. The MCP
      tool list/call endpoints, the agent graph view, and the advisory
      run-status/progress views now gate on the application role
      (``is_officer()`` or ``is_system_admin()``). A Viewer with
      ``is_staff=True`` (mis-provisioned via ``create_officer --role
      viewer``) must NOT gain access.

P-01: The ``create_officer`` management command no longer sets
      ``is_staff=True`` unconditionally. A Viewer provisioned via
      ``--role viewer`` gets ``is_staff=False``.

D-12: The MCP tool call view binds ``actor``/``actor_id`` to the
      authenticated request user. Client-supplied ``actor``/``actor_id``
      values are stripped from the JSON body and cannot override the
      authenticated identity.

D-13: The ``create_draft_advisory_record`` tool enforces ``is_officer()``
      at the tool boundary. A Viewer (or missing actor) is rejected with
      an error dict; no ``Advisory`` row is created.

D-14: The ``create_follow_up_task_after_approval`` service prevents
      task-owner impersonation. The ``actor`` must be the officer who
      approved the advisory (``officer_id``) or a System Administrator.
      An ordinary officer cannot create a task attributed to a different
      officer.

Out of scope: Phase A/B/C security behavior (covered by existing test
files), D-02 (task data confidentiality — Priority 2), D-08/D-09/D-11
(task workflow-state — Priority 3), D-04/D-05/D-06/D-07/D-10/P-08
(audit quality — Priority 4).
"""
from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from io import StringIO

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_staff_viewer():
    """Create a Viewer with is_staff=True (simulates the mis-provisioning
    that create_officer --role viewer used to cause). Used to verify the
    is_staff-based gates are now closed."""
    user, _ = User.objects.get_or_create(
        username="phase_d_staff_viewer",
        defaults={
            "role": User.Role.VIEWER,
            "full_name": "Staff Viewer",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
            "is_active": True,
            "approval_status": "approved",
        },
    )
    user.is_staff = True
    user.is_superuser = False
    user.is_active = True
    user.approval_status = "approved"
    user.save()
    return user


def _staff_viewer_client():
    c = Client()
    c.force_login(_make_staff_viewer())
    return c


# ---------------------------------------------------------------------------
# D-01: is_staff no longer grants access to role-gated endpoints
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_staff_viewer_denied_mcp_tool_list():
    """A Viewer with is_staff=True must NOT access /mcp/tools/ (D-01).
    Previously, the is_staff check let mis-provisioned Viewers enumerate
    the full tool catalogue including action tools.
    """
    c = _staff_viewer_client()
    r = c.get("/mcp/tools/")
    assert r.status_code == 403, (
        f"Staff Viewer should be denied /mcp/tools/, got {r.status_code}"
    )


@pytest.mark.django_db
def test_staff_viewer_denied_mcp_tool_call():
    """A Viewer with is_staff=True must NOT call MCP tools (D-01)."""
    c = _staff_viewer_client()
    r = c.post(
        "/mcp/tools/get_cluster_plot_history/call/",
        data=json.dumps({"cluster_id": "KACH-01"}),
        content_type="application/json",
    )
    assert r.status_code == 403, (
        f"Staff Viewer should be denied tool call, got {r.status_code}"
    )


@pytest.mark.django_db
def test_staff_viewer_denied_agent_graph():
    """A Viewer with is_staff=True must NOT access /agents/graph/ (D-01).
    This preserves the existing test_viewer_cannot_open_agent_graph
    assertion for the default viewer fixture (which has is_staff=False)
    and extends it to the mis-provisioned case.
    """
    c = _staff_viewer_client()
    r = c.get("/agents/graph/")
    assert r.status_code == 403, (
        f"Staff Viewer should be denied /agents/graph/, got {r.status_code}"
    )


@pytest.mark.django_db
def test_staff_viewer_denied_other_users_advisory_run():
    """A Viewer with is_staff=True must NOT read another user's advisory
    run status (D-01). Previously, is_staff was the bypass.
    """
    from apps.agents.models import AdvisoryRun
    from tests.factories.models import AdvisoryFactory
    from apps.accounts.models import User as U

    # Create a run owned by a different user (an officer)
    officer = U.objects.create(
        username="phase_d_run_owner",
        role="extension_officer",
        full_name="Run Owner",
        sub_county="Nyatike",
        ward="Kachieng",
        is_active=True,
        approval_status="approved",
    )
    adv = AdvisoryFactory()
    from apps.clusters.models import FarmerCluster
    from tests.factories.models import FarmerClusterFactory
    cluster = FarmerCluster.objects.first() or FarmerClusterFactory()
    run = AdvisoryRun.objects.create(
        requested_by=officer,
        cluster=cluster,
        status="queued",
    )

    c = _staff_viewer_client()
    r = c.get(f"/advisories/runs/{run.run_id}/")
    assert r.status_code == 403, (
        f"Staff Viewer should be denied another user's run status, got {r.status_code}"
    )


@pytest.mark.django_db
def test_officer_allowed_mcp_tool_list(officer_client):
    """An Extension Officer can still access /mcp/tools/ (D-01 regression)."""
    r = officer_client.get("/mcp/tools/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_system_admin_allowed_mcp_tool_list(system_admin_client):
    """A System Administrator can access /mcp/tools/ (D-01 regression).
    Note: system_admin fixture has is_staff=False, so this also confirms
    the gate is role-based, not is_staff-based.
    """
    r = system_admin_client.get("/mcp/tools/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_officer_allowed_agent_graph(officer_client):
    """An Extension Officer can still access /agents/graph/ (D-01 regression)."""
    r = officer_client.get("/agents/graph/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_officer_can_view_own_advisory_run(officer_client, officer):
    """An officer can view their own advisory run status (D-01 regression)."""
    from apps.agents.models import AdvisoryRun
    from apps.clusters.models import FarmerCluster

    cluster = FarmerCluster.objects.first()
    if cluster is None:
        from tests.factories.models import FarmerClusterFactory
        cluster = FarmerClusterFactory()
    run = AdvisoryRun.objects.create(
        requested_by=officer,
        cluster=cluster,
        status="queued",
    )
    r = officer_client.get(f"/advisories/runs/{run.run_id}/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_officer_can_view_other_officers_advisory_run(officer_client):
    """An officer can view another officer's advisory run status (D-01).
    Collaboration across officers is accepted per the governance policy.
    """
    from apps.agents.models import AdvisoryRun
    from apps.accounts.models import User as U
    from apps.clusters.models import FarmerCluster

    other = U.objects.create(
        username="phase_d_other_officer_run",
        role="extension_officer",
        full_name="Other Officer",
        sub_county="Nyatike",
        ward="Kachieng",
        is_active=True,
        approval_status="approved",
    )
    cluster = FarmerCluster.objects.first()
    if cluster is None:
        from tests.factories.models import FarmerClusterFactory
        cluster = FarmerClusterFactory()
    run = AdvisoryRun.objects.create(
        requested_by=other,
        cluster=cluster,
        status="queued",
    )
    r = officer_client.get(f"/advisories/runs/{run.run_id}/")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# P-01: create_officer no longer grants is_staff to viewers
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_create_officer_viewer_does_not_get_is_staff(db):
    """create_officer --role viewer must NOT set is_staff=True (P-01)."""
    call_command(
        "create_officer",
        username="phase_d_cmd_viewer",
        full_name="Cmd Viewer",
        role="viewer",
        sub_county="Nyatike",
        ward="Kachieng",
        stdout=StringIO(),
    )
    user = User.objects.get(username="phase_d_cmd_viewer")
    assert user.role == "viewer"
    assert user.is_staff is False, (
        "create_officer --role viewer must not grant is_staff=True"
    )
    assert user.is_superuser is False


@pytest.mark.django_db
def test_create_officer_extension_officer_does_not_get_is_staff(db):
    """create_officer --role extension_officer must NOT set is_staff=True (P-01).
    The application role is the source of truth; Django admin access is
    a separate privilege granted explicitly via the Django admin UI.
    """
    call_command(
        "create_officer",
        username="phase_d_cmd_officer",
        full_name="Cmd Officer",
        role="extension_officer",
        sub_county="Nyatike",
        ward="Kachieng",
        stdout=StringIO(),
    )
    user = User.objects.get(username="phase_d_cmd_officer")
    assert user.role == "extension_officer"
    assert user.is_staff is False, (
        "create_officer must not grant is_staff=True automatically"
    )
    assert user.is_superuser is False


@pytest.mark.django_db
def test_create_officer_supervisor_does_not_get_is_staff(db):
    """create_officer --role supervisor must NOT set is_staff=True (P-01)."""
    call_command(
        "create_officer",
        username="phase_d_cmd_supervisor",
        full_name="Cmd Supervisor",
        role="supervisor",
        sub_county="Nyatike",
        ward="Kachieng",
        stdout=StringIO(),
    )
    user = User.objects.get(username="phase_d_cmd_supervisor")
    assert user.role == "supervisor"
    assert user.is_staff is False
    assert user.is_superuser is False


# ---------------------------------------------------------------------------
# D-12: MCP tool call binds actor to authenticated user
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_mcp_tool_call_strips_forged_actor_id(officer_client, officer):
    """A client-supplied actor_id must NOT override the authenticated user (D-12).
    The audit event for the tool call must be attributed to the authenticated
    officer, not the forged actor_id.
    """
    from apps.audit.models import AuditEvent
    from apps.accounts.models import User as U

    # Create a different user to attempt impersonation
    other = U.objects.create(
        username="phase_d_forged_actor",
        role="extension_officer",
        full_name="Forged Actor",
        sub_county="Nyatike",
        ward="Kachieng",
        is_active=True,
        approval_status="approved",
    )

    before = AuditEvent.objects.filter(actor_id=other.id).count()
    r = officer_client.post(
        "/mcp/tools/get_cluster_plot_history/call/",
        data=json.dumps({
            "cluster_id": "KACH-01",
            "actor_id": other.id,  # forged — must be stripped
        }),
        content_type="application/json",
    )
    # The tool call should succeed (200) but attribute to the officer, not 'other'
    assert r.status_code == 200
    after = AuditEvent.objects.filter(actor_id=other.id).count()
    assert after == before, (
        "Forged actor_id must NOT appear in audit events — the authenticated user is the actor"
    )


@pytest.mark.django_db
def test_mcp_tool_call_strips_forged_actor_object(officer_client, officer):
    """A client-supplied 'actor' key in the body must NOT cause a TypeError
    or override the authenticated user (D-12). The body 'actor' key is
    popped before the tool function is called.
    """
    r = officer_client.post(
        "/mcp/tools/get_cluster_plot_history/call/",
        data=json.dumps({
            "cluster_id": "KACH-01",
            "actor": "forged-actor-value",  # must be stripped (would cause TypeError if passed)
        }),
        content_type="application/json",
    )
    assert r.status_code == 200, (
        f"Forged 'actor' key must be stripped, got {r.status_code}: {r.content[:200]}"
    )


@pytest.mark.django_db
def test_mcp_tool_call_without_actor_in_body(officer_client, officer):
    """A tool call with no actor/actor_id in the body must work normally (D-12
    regression — the actor binding must not break legitimate calls).
    """
    r = officer_client.post(
        "/mcp/tools/get_cluster_plot_history/call/",
        data=json.dumps({"cluster_id": "KACH-01"}),
        content_type="application/json",
    )
    assert r.status_code == 200


@pytest.mark.django_db
def test_mcp_tool_call_attributes_audit_to_authenticated_user(officer_client, officer):
    """The audit event for a tool call must be attributed to the authenticated
    request.user (D-12), not to any client-supplied value.
    """
    from apps.audit.models import AuditEvent

    before = AuditEvent.objects.filter(actor_id=officer.id).count()
    r = officer_client.post(
        "/mcp/tools/get_cluster_plot_history/call/",
        data=json.dumps({"cluster_id": "KACH-01"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    after = AuditEvent.objects.filter(actor_id=officer.id).count()
    assert after > before, (
        "Tool call audit event must be attributed to the authenticated officer"
    )


# ---------------------------------------------------------------------------
# D-13: create_draft_advisory_record enforces is_officer() at the tool boundary
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_create_draft_advisory_record_rejects_viewer_actor(viewer):
    """A Viewer calling create_draft_advisory_record directly must be rejected
    (D-13). No Advisory row is created. This guards the tool boundary even
    if a future transport bypasses the HTTP view.
    """
    from apps.mcp_tools.tools import create_draft_advisory_record
    from apps.advisories.models import Advisory

    before = Advisory.objects.count()
    result = create_draft_advisory_record(
        advisory_text="Test body " * 20,
        summary="Test summary",
        recommendation_type="plant",
        confidence="medium",
        limitations="None",
        evidence_links=[],
        model_metadata={"model": "test", "provider": "none"},
        cluster_id="KACH-01",
        actor_id=viewer.id,
    )
    after = Advisory.objects.count()
    assert "error" in result, "Viewer actor must be rejected"
    assert "not authorized" in result["error"].lower()
    assert after == before, "No Advisory row should be created for a Viewer actor"


@pytest.mark.django_db
def test_create_draft_advisory_record_rejects_missing_actor():
    """A missing actor_id must be rejected (D-13). No Advisory row is created."""
    from apps.mcp_tools.tools import create_draft_advisory_record
    from apps.advisories.models import Advisory

    before = Advisory.objects.count()
    result = create_draft_advisory_record(
        advisory_text="Test body " * 20,
        summary="Test summary",
        recommendation_type="plant",
        confidence="medium",
        limitations="None",
        evidence_links=[],
        model_metadata={"model": "test", "provider": "none"},
        cluster_id="KACH-01",
        actor_id=None,
    )
    after = Advisory.objects.count()
    assert "error" in result
    assert "Actor is required" in result["error"]
    assert after == before


@pytest.mark.django_db
def test_create_draft_advisory_record_rejects_nonexistent_actor():
    """A nonexistent actor_id must be rejected (D-13). No Advisory row is created."""
    from apps.mcp_tools.tools import create_draft_advisory_record
    from apps.advisories.models import Advisory

    before = Advisory.objects.count()
    result = create_draft_advisory_record(
        advisory_text="Test body " * 20,
        summary="Test summary",
        recommendation_type="plant",
        confidence="medium",
        limitations="None",
        evidence_links=[],
        model_metadata={"model": "test", "provider": "none"},
        cluster_id="KACH-01",
        actor_id=999999,  # nonexistent
    )
    after = Advisory.objects.count()
    assert "error" in result
    assert "not found" in result["error"].lower()
    assert after == before


@pytest.mark.django_db
def test_create_draft_advisory_record_allows_officer_actor(officer):
    """An Extension Officer actor can create a draft advisory (D-13 regression).
    The created draft must have status=DRAFT (human approval still required).
    """
    from apps.mcp_tools.tools import create_draft_advisory_record
    from apps.advisories.models import Advisory

    # Ensure a cluster exists
    from tests.factories.models import FarmerClusterFactory
    FarmerClusterFactory(cluster_id="KACH-D13")

    result = create_draft_advisory_record(
        advisory_text="Officer-created draft body " * 4,
        summary="Officer draft summary",
        recommendation_type="plant",
        confidence="medium",
        limitations="None",
        evidence_links=[],
        model_metadata={"model": "test", "provider": "none"},
        cluster_id="KACH-D13",
        actor_id=officer.id,
    )
    assert "advisory_id" in result, (
        f"Officer actor should create a draft, got: {result}"
    )
    adv = Advisory.objects.get(pk=result["advisory_id"])
    assert adv.status == Advisory.Status.DRAFT
    assert adv.created_by_id == officer.id


# ---------------------------------------------------------------------------
# D-14: create_follow_up_task_after_approval prevents impersonation
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_create_follow_up_task_rejects_impersonation(officer, supervisor):
    """An officer cannot create a task attributed to a different officer (D-14).
    Officer A approves an advisory, then Officer B tries to create a task
    with officer_id=officer_a.id. The service must reject.
    """
    from apps.tasks.service import create_follow_up_task_after_approval
    from apps.tasks.models import FollowUpTask
    from apps.approvals.models import OfficerApproval
    from apps.advisories.models import Advisory
    from tests.factories.models import AdvisoryFactory

    adv = AdvisoryFactory(status=Advisory.Status.DRAFT)
    # Officer approves the advisory
    OfficerApproval.objects.create(
        advisory=adv, officer=officer, decision=OfficerApproval.Decision.APPROVED
    )
    adv.status = Advisory.Status.APPROVED
    adv.save()

    before = FollowUpTask.objects.count()
    # Supervisor (a different officer) tries to create a task with officer_id=officer.id
    # Wait — supervisor IS an officer per is_officer(). So this tests: can a supervisor
    # create a task attributed to the officer who approved? Per D-14, only if
    # actor.id == officer_id or actor.is_system_admin(). Supervisor is not the officer
    # and is not a system admin → must be rejected.
    result = create_follow_up_task_after_approval(
        approved_advisory_id=adv.id,
        officer_id=officer.id,  # the officer who approved
        task_type="field_visit",
        ward="Kachieng",
        actor=supervisor,  # a different officer (supervisor)
    )
    after = FollowUpTask.objects.count()
    assert "error" in result, "Impersonation must be rejected"
    assert "not authorized" in result["error"].lower()
    assert after == before, "No task should be created on impersonation attempt"


@pytest.mark.django_db
def test_create_follow_up_task_same_officer_succeeds(officer):
    """The officer who approved can create their own task (D-14 regression).
    actor=officer, officer_id=officer.id → must succeed.
    """
    from apps.tasks.service import create_follow_up_task_after_approval
    from apps.tasks.models import FollowUpTask
    from apps.approvals.models import OfficerApproval
    from apps.advisories.models import Advisory
    from tests.factories.models import AdvisoryFactory

    adv = AdvisoryFactory(status=Advisory.Status.DRAFT)
    OfficerApproval.objects.create(
        advisory=adv, officer=officer, decision=OfficerApproval.Decision.APPROVED
    )
    adv.status = Advisory.Status.APPROVED
    adv.save()

    result = create_follow_up_task_after_approval(
        approved_advisory_id=adv.id,
        officer_id=officer.id,
        task_type="field_visit",
        ward="Kachieng",
        actor=officer,
    )
    assert "task_id" in result, f"Same-officer creation must succeed, got: {result}"
    assert FollowUpTask.objects.filter(id=result["task_id"]).exists()


@pytest.mark.django_db
def test_create_follow_up_task_system_admin_on_behalf_succeeds(system_admin, officer):
    """A System Administrator can create a task on behalf of the approving
    officer (D-14). This is the only documented authorized delegation path.
    """
    from apps.tasks.service import create_follow_up_task_after_approval
    from apps.tasks.models import FollowUpTask
    from apps.approvals.models import OfficerApproval
    from apps.advisories.models import Advisory
    from tests.factories.models import AdvisoryFactory

    adv = AdvisoryFactory(status=Advisory.Status.DRAFT)
    OfficerApproval.objects.create(
        advisory=adv, officer=officer, decision=OfficerApproval.Decision.APPROVED
    )
    adv.status = Advisory.Status.APPROVED
    adv.save()

    result = create_follow_up_task_after_approval(
        approved_advisory_id=adv.id,
        officer_id=officer.id,
        task_type="field_visit",
        ward="Kachieng",
        actor=system_admin,
    )
    assert "task_id" in result, (
        f"System admin acting on behalf of officer must succeed, got: {result}"
    )
    task = FollowUpTask.objects.get(id=result["task_id"])
    assert task.owner_id == officer.id


@pytest.mark.django_db
def test_create_follow_up_task_rejects_missing_actor(officer):
    """A missing actor must be rejected (D-14). No task is created."""
    from apps.tasks.service import create_follow_up_task_after_approval
    from apps.tasks.models import FollowUpTask
    from apps.approvals.models import OfficerApproval
    from apps.advisories.models import Advisory
    from tests.factories.models import AdvisoryFactory

    adv = AdvisoryFactory(status=Advisory.Status.DRAFT)
    OfficerApproval.objects.create(
        advisory=adv, officer=officer, decision=OfficerApproval.Decision.APPROVED
    )
    adv.status = Advisory.Status.APPROVED
    adv.save()

    before = FollowUpTask.objects.count()
    result = create_follow_up_task_after_approval(
        approved_advisory_id=adv.id,
        officer_id=officer.id,
        task_type="field_visit",
        ward="Kachieng",
        actor=None,
    )
    after = FollowUpTask.objects.count()
    assert "error" in result
    assert "Actor is required" in result["error"]
    assert after == before


@pytest.mark.django_db
def test_create_follow_up_task_approval_gate_still_enforced(officer):
    """The approval gate is still enforced (D-14 regression). Without an
    APPROVED OfficerApproval, no task is created — even if actor matches.
    """
    from apps.tasks.service import create_follow_up_task_after_approval
    from apps.tasks.models import FollowUpTask
    from apps.advisories.models import Advisory
    from tests.factories.models import AdvisoryFactory

    adv = AdvisoryFactory(status=Advisory.Status.DRAFT)
    # No OfficerApproval created
    adv.status = Advisory.Status.APPROVED
    adv.save()

    before = FollowUpTask.objects.count()
    result = create_follow_up_task_after_approval(
        approved_advisory_id=adv.id,
        officer_id=officer.id,
        task_type="field_visit",
        ward="Kachieng",
        actor=officer,
    )
    after = FollowUpTask.objects.count()
    assert "error" in result
    assert "Approval gate" in result["error"]
    assert after == before


# ---------------------------------------------------------------------------
# Regression: existing security tests still pass
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_viewer_cannot_open_agent_graph_still_passes(viewer_client):
    """Regression: the default viewer (is_staff=False) is still denied
    /agents/graph/. This is the existing test_security.py assertion.
    """
    r = viewer_client.get("/agents/graph/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_viewer_cannot_request_advisory_still_passes(viewer_client):
    """Regression: a viewer is still denied /advisories/request/."""
    r = viewer_client.get("/advisories/request/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_viewer_cannot_approve_advisory_still_passes(viewer_client):
    """Regression: a viewer is still denied the approval gate."""
    from tests.factories.models import AdvisoryFactory
    from apps.advisories.models import Advisory
    adv = AdvisoryFactory(cluster__cluster_id="KACH-01", status=Advisory.Status.DRAFT)
    r = viewer_client.post(f"/approvals/{adv.id}/", {"decision": "approved"})
    assert r.status_code == 403
