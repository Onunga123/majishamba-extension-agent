"""Phase 3 regression tests — task semantic audit events (F-12) and
health-route integrity (F-10).

F-12 covers the missing semantic audit events for task state changes.
The audit infrastructure already reserved action names
(``task:complete``, ``task:verify``, ``task:finding``) and the audit
middleware already excludes the ``/complete/``, ``/verify/``, and
``/findings/`` suffixes from HTTP-level logging — but the views never
called ``log_audit_event`` for these state transitions. The result was
that no audit event was logged at all for any task state change. F-12
adds the semantic ``log_audit_event`` calls to ``TaskFieldFindingView``,
``TaskCompleteView``, and ``TaskVerifyView`` after the corresponding
state mutation has been persisted, so a failed save does not produce a
misleading success event.

F-10 covers the duplicate ``/health/`` URL mounting that exposed the
entire dashboard app under ``/health/`` and the AccountStatusMiddleware
exemption that used ``/health/`` as a prefix. The route was narrowed
to a single ``HealthCheckView`` at ``/health/`` and the middleware
exemption was narrowed to the exact path ``/health/``.

Out of scope: F-03 (AuditTrailView removal — verified by no-routes
inspection), F-11 (account_permissions templatetag removal — verified
by no-template-loads inspection), F-09 (superuser task verify bypass
— deferred policy decision), and the three pre-existing LLM-provider
test failures.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers — local user factories (match the conventions in
# tests/security/test_phase_b_audit_visibility.py).
# ---------------------------------------------------------------------------
def _make_user(username, role, full_name, *, is_staff=False):
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={
            "role": role,
            "full_name": full_name,
            "sub_county": "Nyatike",
            "ward": "Kachieng",
            "is_active": True,
            "approval_status": "approved",
            "is_staff": is_staff,
        },
    )
    user.is_active = True
    user.approval_status = "approved"
    user.is_staff = is_staff
    user.set_password("test-pw-123")
    user.save()
    return user


def _make_officer():
    return _make_user("phase3_officer", "extension_officer", "Phase3 Officer")


def _make_supervisor():
    return _make_user("phase3_supervisor", "supervisor", "Phase3 Supervisor")


def _make_viewer():
    return _make_user("phase3_viewer", "viewer", "Phase3 Viewer")


def _make_system_admin():
    return _make_user("phase3_system_admin", "system_admin", "Phase3 Sys Admin", is_staff=False)


def _make_task(owner=None, status="assigned"):
    """Create a FollowUpTask with an approved advisory."""
    from tests.factories.models import AdvisoryFactory
    from apps.tasks.models import FollowUpTask

    adv = AdvisoryFactory(status="approved")
    return FollowUpTask.objects.create(
        approved_advisory=adv,
        task_type=FollowUpTask.TaskType.FIELD_VISIT,
        deadline="2030-01-01",
        status=status,
        owner=owner,
    )


def _make_finding(task, submitted_by, visit_date="2026-10-15"):
    from apps.tasks.models import FieldFinding

    return FieldFinding.objects.create(
        task=task,
        visit_date=visit_date,
        observations="Phase 3 test observation",
        missing_information="",
        submitted_by=submitted_by,
    )


def _audit_events_for_task(task_id, action=None):
    """Return all AuditEvent rows targeting the given task_id, optionally
    filtered by action."""
    from apps.audit.models import AuditEvent

    qs = AuditEvent.objects.filter(target_type="FollowUpTask", target_id=str(task_id))
    if action is not None:
        qs = qs.filter(action=action)
    return list(qs)


# ---------------------------------------------------------------------------
# F-12: Task completion — audit event recording
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_task_complete_records_audit_event():
    """F-12 regression: a successful task completion records a
    ``task:complete`` audit event targeting the task, with the
    authenticated officer as actor.
    """
    from apps.tasks.models import FollowUpTask

    officer = _make_officer()
    task = _make_task(owner=officer, status="assigned")

    c = Client(); c.force_login(officer)
    r = c.post(f"/tasks/{task.id}/complete/")
    assert r.status_code == 302
    task.refresh_from_db()
    assert task.status == FollowUpTask.Status.COMPLETED

    events = _audit_events_for_task(task.id, action="task:complete")
    assert len(events) == 1, (
        f"Expected exactly 1 task:complete audit event, got {len(events)}"
    )
    event = events[0]
    assert event.actor_id == officer.id
    assert event.target_type == "FollowUpTask"
    assert event.target_id == str(task.id)
    # Metadata includes the previous and new status (non-sensitive)
    assert event.metadata.get("previous_status") == "assigned"
    assert event.metadata.get("new_status") == "completed"
    assert event.metadata.get("task_id") == task.id


@pytest.mark.django_db
def test_task_complete_does_not_record_event_on_invalid_state():
    """F-12 regression: completing a task in an invalid state (e.g.
    COMPLETED) does NOT produce a ``task:complete`` audit event — the
    403 is raised BEFORE the audit call.
    """
    officer = _make_officer()
    task = _make_task(owner=officer, status="completed")

    c = Client(); c.force_login(officer)
    r = c.post(f"/tasks/{task.id}/complete/")
    assert r.status_code == 403

    events = _audit_events_for_task(task.id, action="task:complete")
    assert events == [], (
        "No task:complete audit event should be recorded for an invalid state rejection"
    )


@pytest.mark.django_db
def test_task_complete_does_not_record_event_on_unauthorized_role():
    """F-12 regression: a Viewer attempting to complete a task does NOT
    produce a ``task:complete`` audit event — the role check 403 is
    raised BEFORE the audit call.
    """
    officer = _make_officer()
    viewer = _make_viewer()
    task = _make_task(owner=officer, status="assigned")

    c = Client(); c.force_login(viewer)
    r = c.post(f"/tasks/{task.id}/complete/")
    assert r.status_code == 403

    events = _audit_events_for_task(task.id, action="task:complete")
    assert events == []


@pytest.mark.django_db
def test_task_complete_no_duplicate_http_event():
    """F-12 regression: the audit middleware excludes the ``/complete/``
    suffix from HTTP-level logging, so only the semantic
    ``task:complete`` event is recorded (no duplicate
    ``http:POST:/tasks/N/complete/`` event).
    """
    officer = _make_officer()
    task = _make_task(owner=officer, status="assigned")

    c = Client(); c.force_login(officer)
    c.post(f"/tasks/{task.id}/complete/")

    from apps.audit.models import AuditEvent

    http_events = list(AuditEvent.objects.filter(
        action=f"http:POST:/tasks/{task.id}/complete/"
    ))
    assert http_events == [], (
        "No http:POST: audit event should be logged for /complete/ "
        "(middleware excludes suffix to avoid duplicates with semantic event)"
    )
    semantic_events = _audit_events_for_task(task.id, action="task:complete")
    assert len(semantic_events) == 1


# ---------------------------------------------------------------------------
# F-12: Task verification — audit event recording
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_task_verify_records_audit_event():
    """F-12 regression: a successful task verification records a
    ``task:verify`` audit event targeting the task, with the
    supervisor as actor.
    """
    from apps.tasks.models import FollowUpTask

    officer = _make_officer()
    supervisor = _make_supervisor()
    task = _make_task(owner=officer, status="completed")
    _make_finding(task, submitted_by=officer)

    c = Client(); c.force_login(supervisor)
    r = c.post(f"/tasks/{task.id}/verify/")
    assert r.status_code == 302
    task.refresh_from_db()
    assert task.status == FollowUpTask.Status.VERIFIED

    events = _audit_events_for_task(task.id, action="task:verify")
    assert len(events) == 1
    event = events[0]
    assert event.actor_id == supervisor.id
    assert event.target_type == "FollowUpTask"
    assert event.target_id == str(task.id)
    assert event.metadata.get("task_id") == task.id
    assert event.metadata.get("verified_by_id") == supervisor.id


@pytest.mark.django_db
def test_task_verify_does_not_record_event_on_invalid_state():
    """F-12 regression: verifying a task in an invalid state (e.g.
    IN_PROGRESS) does NOT produce a ``task:verify`` audit event.
    """
    officer = _make_officer()
    supervisor = _make_supervisor()
    task = _make_task(owner=officer, status="in_progress")
    _make_finding(task, submitted_by=officer)

    c = Client(); c.force_login(supervisor)
    r = c.post(f"/tasks/{task.id}/verify/")
    assert r.status_code == 403

    events = _audit_events_for_task(task.id, action="task:verify")
    assert events == []


@pytest.mark.django_db
def test_task_verify_does_not_record_event_when_no_findings():
    """F-12 regression: verifying a task with no findings does NOT
    produce a ``task:verify`` audit event — the validation 403 is
    raised BEFORE the audit call.
    """
    officer = _make_officer()
    supervisor = _make_supervisor()
    task = _make_task(owner=officer, status="completed")
    # No findings created

    c = Client(); c.force_login(supervisor)
    r = c.post(f"/tasks/{task.id}/verify/")
    assert r.status_code == 403

    events = _audit_events_for_task(task.id, action="task:verify")
    assert events == []


@pytest.mark.django_db
def test_task_verify_does_not_record_event_on_self_verification():
    """F-12 regression: a supervisor attempting to verify their own
    finding does NOT produce a ``task:verify`` audit event — the
    self-verification 403 is raised BEFORE the audit call.
    """
    supervisor = _make_supervisor()
    task = _make_task(owner=supervisor, status="completed")
    _make_finding(task, submitted_by=supervisor)

    c = Client(); c.force_login(supervisor)
    r = c.post(f"/tasks/{task.id}/verify/")
    assert r.status_code == 403

    events = _audit_events_for_task(task.id, action="task:verify")
    assert events == []


@pytest.mark.django_db
def test_task_verify_does_not_record_event_on_unauthorized_role():
    """F-12 regression: an Officer attempting to verify a task does NOT
    produce a ``task:verify`` audit event — only Supervisors can verify.
    """
    officer = _make_officer()
    other_officer = _make_user("phase3_other_officer", "extension_officer", "Phase3 Other Officer")
    task = _make_task(owner=officer, status="completed")
    _make_finding(task, submitted_by=officer)

    c = Client(); c.force_login(other_officer)
    r = c.post(f"/tasks/{task.id}/verify/")
    assert r.status_code == 403

    events = _audit_events_for_task(task.id, action="task:verify")
    assert events == []


@pytest.mark.django_db
def test_task_verify_no_duplicate_http_event():
    """F-12 regression: the audit middleware excludes the ``/verify/``
    suffix from HTTP-level logging, so only the semantic ``task:verify``
    event is recorded.
    """
    officer = _make_officer()
    supervisor = _make_supervisor()
    task = _make_task(owner=officer, status="completed")
    _make_finding(task, submitted_by=officer)

    c = Client(); c.force_login(supervisor)
    c.post(f"/tasks/{task.id}/verify/")

    from apps.audit.models import AuditEvent

    http_events = list(AuditEvent.objects.filter(
        action=f"http:POST:/tasks/{task.id}/verify/"
    ))
    assert http_events == []
    semantic_events = _audit_events_for_task(task.id, action="task:verify")
    assert len(semantic_events) == 1


# ---------------------------------------------------------------------------
# F-12: Task finding submission — audit event recording
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_task_finding_records_audit_event():
    """F-12 regression: a successful field-finding submission records a
    ``task:finding`` audit event targeting the task, with the officer
    as actor.
    """
    officer = _make_officer()
    task = _make_task(owner=officer, status="assigned")

    c = Client(); c.force_login(officer)
    r = c.post(f"/tasks/{task.id}/findings/", {
        "visit_date": "2026-10-15",
        "observations": "Test observation text",
        "missing_information": "",
    })
    assert r.status_code == 302

    events = _audit_events_for_task(task.id, action="task:finding")
    assert len(events) == 1
    event = events[0]
    assert event.actor_id == officer.id
    assert event.target_type == "FollowUpTask"
    assert event.target_id == str(task.id)
    assert event.metadata.get("task_id") == task.id
    assert event.metadata.get("previous_status") == "assigned"
    assert event.metadata.get("transitioned_to") == "in_progress"


@pytest.mark.django_db
def test_task_finding_records_audit_event_no_status_transition():
    """F-12 regression: when the task is already IN_PROGRESS, finding
    submission records an audit event with previous_status ==
    transitioned_to == 'in_progress' (no transition).
    """
    from apps.tasks.models import FollowUpTask

    officer = _make_officer()
    task = _make_task(owner=officer, status="in_progress")

    c = Client(); c.force_login(officer)
    r = c.post(f"/tasks/{task.id}/findings/", {
        "visit_date": "2026-10-15",
        "observations": "Second observation",
        "missing_information": "",
    })
    assert r.status_code == 302
    task.refresh_from_db()
    assert task.status == FollowUpTask.Status.IN_PROGRESS  # unchanged

    events = _audit_events_for_task(task.id, action="task:finding")
    assert len(events) == 1
    event = events[0]
    assert event.metadata.get("previous_status") == "in_progress"
    assert event.metadata.get("transitioned_to") == "in_progress"


@pytest.mark.django_db
def test_task_finding_does_not_record_event_on_invalid_state():
    """F-12 regression: submitting findings on a COMPLETED task does NOT
    produce a ``task:finding`` audit event — the state-check 403 is
    raised BEFORE the audit call.
    """
    officer = _make_officer()
    task = _make_task(owner=officer, status="completed")

    c = Client(); c.force_login(officer)
    r = c.post(f"/tasks/{task.id}/findings/", {
        "visit_date": "2026-10-15",
        "observations": "Test",
        "missing_information": "",
    })
    assert r.status_code == 403

    events = _audit_events_for_task(task.id, action="task:finding")
    assert events == []


@pytest.mark.django_db
def test_task_finding_does_not_record_event_on_unauthorized_role():
    """F-12 regression: a Viewer attempting to submit findings does NOT
    produce a ``task:finding`` audit event.
    """
    officer = _make_officer()
    viewer = _make_viewer()
    task = _make_task(owner=officer, status="assigned")

    c = Client(); c.force_login(viewer)
    r = c.post(f"/tasks/{task.id}/findings/", {
        "visit_date": "2026-10-15",
        "observations": "Test",
        "missing_information": "",
    })
    assert r.status_code == 403

    events = _audit_events_for_task(task.id, action="task:finding")
    assert events == []


@pytest.mark.django_db
def test_task_finding_no_duplicate_http_event():
    """F-12 regression: the audit middleware excludes the ``/findings/``
    suffix from HTTP-level logging, so only the semantic ``task:finding``
    event is recorded.
    """
    officer = _make_officer()
    task = _make_task(owner=officer, status="assigned")

    c = Client(); c.force_login(officer)
    c.post(f"/tasks/{task.id}/findings/", {
        "visit_date": "2026-10-15",
        "observations": "Test",
        "missing_information": "",
    })

    from apps.audit.models import AuditEvent

    http_events = list(AuditEvent.objects.filter(
        action=f"http:POST:/tasks/{task.id}/findings/"
    ))
    assert http_events == []
    semantic_events = _audit_events_for_task(task.id, action="task:finding")
    assert len(semantic_events) == 1


@pytest.mark.django_db
def test_task_finding_audit_metadata_excludes_observations():
    """F-12 regression: the audit event metadata must NOT include the
    finding's free-text observation content (potential PII / sensitive
    field content). Only structural fields (task_id, finding_id,
    previous_status, transitioned_to) are recorded.
    """
    officer = _make_officer()
    task = _make_task(owner=officer, status="assigned")

    sensitive_text = "Secret farmer observation text"
    c = Client(); c.force_login(officer)
    c.post(f"/tasks/{task.id}/findings/", {
        "visit_date": "2026-10-15",
        "observations": sensitive_text,
        "missing_information": "",
    })

    events = _audit_events_for_task(task.id, action="task:finding")
    assert len(events) == 1
    event = events[0]
    # The sensitive observation text must NOT appear in the audit metadata
    assert sensitive_text not in str(event.metadata)
    assert sensitive_text not in str(event.inputs_summary)
    assert sensitive_text not in str(event.outputs_summary)


# ---------------------------------------------------------------------------
# F-12: Existing task behavior preserved (regression guard)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_task_complete_response_unchanged():
    """F-12 regression: the redirect response after successful task
    completion is unchanged (302 to tasks:detail).
    """
    officer = _make_officer()
    task = _make_task(owner=officer, status="assigned")

    c = Client(); c.force_login(officer)
    r = c.post(f"/tasks/{task.id}/complete/")
    assert r.status_code == 302
    assert f"/tasks/{task.id}/" in r["Location"]


@pytest.mark.django_db
def test_task_verify_response_unchanged():
    """F-12 regression: the redirect response after successful task
    verification is unchanged (302 to tasks:detail).
    """
    officer = _make_officer()
    supervisor = _make_supervisor()
    task = _make_task(owner=officer, status="completed")
    _make_finding(task, submitted_by=officer)

    c = Client(); c.force_login(supervisor)
    r = c.post(f"/tasks/{task.id}/verify/")
    assert r.status_code == 302
    assert f"/tasks/{task.id}/" in r["Location"]


@pytest.mark.django_db
def test_task_finding_response_unchanged():
    """F-12 regression: the redirect response after successful finding
    submission is unchanged (302 to tasks:detail).
    """
    officer = _make_officer()
    task = _make_task(owner=officer, status="assigned")

    c = Client(); c.force_login(officer)
    r = c.post(f"/tasks/{task.id}/findings/", {
        "visit_date": "2026-10-15",
        "observations": "Test",
        "missing_information": "",
    })
    assert r.status_code == 302
    assert f"/tasks/{task.id}/" in r["Location"]


# ---------------------------------------------------------------------------
# F-10: /health/ route integrity
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_health_endpoint_returns_200_json():
    """F-10 regression: GET /health/ returns 200 with the JSON health
    payload. The route was narrowed to a single HealthCheckView.
    """
    c = Client()
    r = c.get("/health/")
    assert r.status_code == 200
    assert r["Content-Type"].startswith("application/json")
    data = r.json()
    assert data["status"] in ("ok", "degraded")
    assert "database" in data
    assert "llm_provider" in data
    assert "version" in data


@pytest.mark.django_db
def test_health_endpoint_does_not_require_authentication():
    """F-10 regression: the health endpoint does not require
    authentication (it's for load balancers and monitoring).
    """
    c = Client()
    # Do not force_login anyone — anonymous request
    r = c.get("/health/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_health_endpoint_secrets_absent():
    """F-10 regression: the health endpoint does not expose API keys
    or secrets (existing assertion preserved from test_production.py).
    """
    c = Client()
    r = c.get("/health/")
    text = r.content.decode("utf-8")
    assert "sk-or-v1" not in text
    assert "PASSWORD" not in text.upper()


@pytest.mark.django_db
def test_health_dashboard_routes_not_shadowed_under_health_prefix():
    """F-10 regression: the dashboard routes (map, audit, about, etc.)
    must NOT be reachable under /health/* — only the JSON health
    endpoint exists at /health/.

    Before the fix, the entire dashboard app was mounted under
    /health/, exposing /health/map/, /health/audit/, /health/about/,
    /health/guidance/, /health/data-sources/, /health/health/ as
    duplicates of the dashboard routes.
    """
    c = Client()
    # These paths must NOT be exposed under /health/ any more
    for shadow_path in (
        "/health/map/",
        "/health/audit/",
        "/health/about/",
        "/health/guidance/",
        "/health/data-sources/",
        # The old /health/health/ (double health) used to map to the
        # HealthCheckView because the dashboard app's health/ route was
        # mounted at /health/. After narrowing /health/ to a single
        # view, /health/health/ should 404.
        "/health/health/",
        # /health/ (the empty dashboard home) used to map to
        # DashboardHomeView at /health/. After the fix, /health/ is the
        # JSON endpoint, not the dashboard home.
    ):
        r = c.get(shadow_path)
        # The shadow route must NOT return 200 — either 404 (not found)
        # or 302 (login redirect, if the path happens to match a
        # different prefix). The previous /health/map/ would have
        # returned 302 to /accounts/login/. After the fix, /health/map/
        # 404s because only /health/ exists.
        assert r.status_code != 200, (
            f"Shadow route {shadow_path} should not be reachable — got {r.status_code}"
        )


@pytest.mark.django_db
def test_health_dashboard_named_route_still_resolves():
    """F-10 regression: the dashboard-internal named route
    ``dashboard:health`` at /dashboard/health/ still resolves (this is
    the HealthCheckView also reachable from the dashboard app's urls).
    The narrowing of /health/ does not affect /dashboard/health/.
    """
    from django.urls import reverse

    url = reverse("dashboard:health")
    assert url == "/dashboard/health/"
    c = Client()
    r = c.get(url)
    assert r.status_code == 200
    assert r["Content-Type"].startswith("application/json")


@pytest.mark.django_db
def test_health_named_route_root_health():
    """F-10 regression: the root-level health route name 'health'
    resolves to /health/ (JSON endpoint). This name was preserved by
    the F-10 URL change.
    """
    from django.urls import reverse

    url = reverse("health")
    assert url == "/health/"


@pytest.mark.django_db
def test_health_account_status_middleware_exemption_narrow():
    """F-10 regression: AccountStatusMiddleware exempts only the exact
    path /health/ (not a /health/ prefix). A non-approved authenticated
    user requesting /dashboard/ is still redirected to login (the
    middleware is NOT bypassed for non-health paths).
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    # Create a PENDING account (not approved)
    pending_user, _ = User.objects.get_or_create(
        username="phase3_pending_user",
        defaults={
            "role": "extension_officer",
            "full_name": "Phase3 Pending",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
            "is_active": True,
            "approval_status": "pending",
        },
    )
    pending_user.is_active = True
    pending_user.approval_status = "pending"
    pending_user.set_password("test-pw-123")
    pending_user.save()

    c = Client()
    c.force_login(pending_user)
    # /dashboard/ is not in _EXEMPT_PATHS and does not start with an
    # exempt prefix — the middleware must redirect to login.
    r = c.get("/dashboard/")
    assert r.status_code in {302, 301}
    assert "/accounts/login/" in r["Location"]


@pytest.mark.django_db
def test_health_account_status_middleware_exemption_applies_to_health():
    """F-10 regression: AccountStatusMiddleware exempts /health/ (exact
    path). A non-approved authenticated user requesting /health/ is
    NOT redirected to login (the health endpoint is for monitoring).
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    pending_user, _ = User.objects.get_or_create(
        username="phase3_pending_health",
        defaults={
            "role": "extension_officer",
            "full_name": "Phase3 Pending Health",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
            "is_active": True,
            "approval_status": "pending",
        },
    )
    pending_user.is_active = True
    pending_user.approval_status = "pending"
    pending_user.set_password("test-pw-123")
    pending_user.save()

    c = Client()
    c.force_login(pending_user)
    r = c.get("/health/")
    # The middleware must NOT redirect — the health endpoint is exempt.
    assert r.status_code == 200
    assert r["Content-Type"].startswith("application/json")


# ---------------------------------------------------------------------------
# F-10: Existing URL names and reverse lookups preserved
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_existing_url_reverse_lookups_preserved():
    """F-10 regression: the existing URL names and reverse lookups used
    by templates and tests still resolve after the /health/ route
    narrowing.
    """
    from django.urls import reverse

    # All the named routes that existed before F-10 must still resolve
    # to the same URLs.
    expected = {
        "dashboard:home": "/dashboard/",
        "dashboard:map": "/dashboard/map/",
        "dashboard:about": "/dashboard/about/",
        "dashboard:guidance": "/dashboard/guidance/",
        "dashboard:data_sources": "/dashboard/data-sources/",
        "dashboard:health": "/dashboard/health/",  # internal HealthCheckView
        "health": "/health/",  # the new root-level health endpoint
        "accounts:login": "/accounts/login/",
        "accounts:logout": "/accounts/logout/",
        "accounts:profile": "/accounts/profile/",
        "audit:list": "/audit/",
        "advisories:list": "/advisories/",
        "tasks:list": "/tasks/",
        "agents:graph": "/agents/graph/",
    }
    for name, url in expected.items():
        assert reverse(name) == url, f"reverse({name!r}) should be {url!r}, got {reverse(name)!r}"


@pytest.mark.django_db
def test_dashboard_audit_legacy_redirect_still_works():
    """F-10 regression: the legacy /dashboard/audit/ route still
    redirects to /audit/ (this is a dashboard-internal route, not the
    /health/ mount).
    """
    c = Client()
    r = c.get("/dashboard/audit/")
    # Anonymous → /dashboard/audit/ is a RedirectView → /audit/ →
    # LoginRequiredMixin redirects to /accounts/login/.
    # The important assertion: no 404 (the route still resolves).
    assert r.status_code in {302, 301}, f"/dashboard/audit/ should redirect, got {r.status_code}"


# ---------------------------------------------------------------------------
# Phase 4: TaskVerifyView atomicity — partial-write rollback
#
# Phase 4 added ``@transaction.atomic`` to ``TaskVerifyView.post`` so that
# the task status change (``task.save``) and the finding verification
# metadata update (``finding.save``) commit or roll back together. The
# partial-write risk: if ``finding.save`` fails AFTER ``task.save``
# succeeds, the task would be left in VERIFIED state but the finding's
# ``verified_by`` / ``verified_at`` would be unset — a visible data
# integrity issue.
#
# This test injects a failure into ``finding.save`` (after the task
# status save would have occurred) and asserts that the transaction
# rolls back the task status to COMPLETED, the finding's verification
# metadata remains unchanged, and no successful ``task:verify`` audit
# event is persisted.
#
# Limitation: this test does NOT exercise the audit-write failure
# scenario, because ``log_audit_event`` swallows its own exceptions
# (per the "audit must never break the call" convention in
# ``apps/audit/service.py``). The ``@transaction.atomic`` wrapper cannot
# detect an audit-write failure to roll back on. See the Phase 4
# read-only review for details.
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_task_verify_rolls_back_task_status_when_finding_save_fails(monkeypatch):
    """Phase 4 regression: if ``finding.save`` fails after ``task.save``
    succeeds, ``@transaction.atomic`` must roll back the task status
    change. The task remains COMPLETED, the finding's ``verified_by`` /
    ``verified_at`` remain unchanged, and no ``task:verify`` audit event
    is persisted.

    The failure is injected via ``monkeypatch.setattr`` on the
    ``FieldFinding.save`` method — the same patching convention used
    elsewhere in the test suite (see ``tests/conftest.py:31`` and
    ``tests/integration/test_dashboard_redesign.py:90``).
    """
    from django.db import DatabaseError
    from apps.tasks.models import FollowUpTask, FieldFinding

    officer = _make_officer()
    supervisor = _make_supervisor()
    task = _make_task(owner=officer, status="completed")
    finding = _make_finding(task, submitted_by=officer)

    # Sanity: before the verify request, the task is COMPLETED and the
    # finding has no verifier.
    assert task.status == FollowUpTask.Status.COMPLETED
    assert finding.verified_by is None
    assert finding.verified_at is None

    # Capture the original save method so we can restore it after the
    # test (monkeypatch does this automatically on teardown).
    original_save = FieldFinding.save

    def failing_save(self, *args, **kwargs):
        # Mimic a database failure (e.g., connection drop, integrity
        # error) when saving the finding's verification metadata. This
        # is called AFTER task.save() has run inside the view, so the
        # task status change is in the transaction but not yet
        # committed (because the view is wrapped in @transaction.atomic).
        raise DatabaseError("Injected failure: finding.save failed after task.save")

    monkeypatch.setattr(FieldFinding, "save", failing_save)

    # Use raise_request_exception=False so the test can inspect the 500
    # response rather than having the DatabaseError propagate out of
    # c.post(). This is the established Django test-client pattern for
    # exercising unhandled-exception code paths.
    c = Client(raise_request_exception=False); c.force_login(supervisor)
    r = c.post(f"/tasks/{task.id}/verify/")
    assert r.status_code == 500, (
        f"Expected 500 from the injected DatabaseError, got {r.status_code}"
    )

    # Restore the original save method before refreshing from the DB.
    monkeypatch.setattr(FieldFinding, "save", original_save)

    # Refresh both objects from the database. The @transaction.atomic
    # wrapper must have rolled back the task status change.
    task.refresh_from_db()
    finding.refresh_from_db()

    # The task must remain COMPLETED (the VERIFIED transition was rolled back).
    assert task.status == FollowUpTask.Status.COMPLETED, (
        f"Task status should be 'completed' after rollback, got {task.status!r}"
    )
    # The finding's verification metadata must be unchanged.
    assert finding.verified_by is None, (
        f"Finding verified_by should be None after rollback, got {finding.verified_by!r}"
    )
    assert finding.verified_at is None, (
        f"Finding verified_at should be None after rollback, got {finding.verified_at!r}"
    )

    # No successful ``task:verify`` audit event should be persisted.
    # The audit call comes AFTER finding.save() in the view, so the
    # DatabaseError is raised before the audit call. The transaction
    # rolls back, so even if an audit row had been created, it would be
    # rolled back too.
    events = _audit_events_for_task(task.id, action="task:verify")
    assert events == [], (
        f"No task:verify audit event should be persisted after rollback, got {events}"
    )


@pytest.mark.django_db
def test_task_verify_atomic_does_not_affect_normal_success_path():
    """Phase 4 regression: ``@transaction.atomic`` must not break the
    normal success path. A successful verification still records the
    audit event, changes the task to VERIFIED, and sets the finding's
    verification metadata. This is a guard against the atomicity change
    accidentally affecting the happy path.
    """
    from apps.tasks.models import FollowUpTask

    officer = _make_officer()
    supervisor = _make_supervisor()
    task = _make_task(owner=officer, status="completed")
    finding = _make_finding(task, submitted_by=officer)

    c = Client(); c.force_login(supervisor)
    r = c.post(f"/tasks/{task.id}/verify/")
    assert r.status_code == 302
    assert f"/tasks/{task.id}/" in r["Location"]

    task.refresh_from_db()
    finding.refresh_from_db()
    assert task.status == FollowUpTask.Status.VERIFIED
    assert finding.verified_by_id == supervisor.id
    assert finding.verified_at is not None

    events = _audit_events_for_task(task.id, action="task:verify")
    assert len(events) == 1
    assert events[0].actor_id == supervisor.id
