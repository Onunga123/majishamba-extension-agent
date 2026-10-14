"""Phase D Priority 2 regression tests — task data confidentiality (D-02).

Covers the approved Priority 2 finding:

D-02: Task list and detail views expose all tasks to every authenticated
      user. Per docs/governance/synthetic_data_notice.md:31,76, officer
      real names must NOT be displayed in any UI surface visible to a
      Viewer role. The about page (templates/dashboard/about.html:32)
      documents "read-only access to ... tasks" for Viewers, so Viewers
      retain read access to the task list and detail pages, but officer
      names (owner, submitted_by, verified_by) are redacted to role
      labels ("Officer", "Supervisor") for Viewers.

D-02 CORRECTION (server-side data minimization): internal field-finding
      content (observations, missing_information, follow_up_notes) is
      restricted to officers and supervisors. For Viewers, the
      ``field_findings`` relation is NOT prefetched and the ``findings``
      context variable is an empty list, so findings text is never
      present in the Viewer's HTTP response — neither in the rendered
      HTML nor in the template context. This is server-side enforcement,
      not template-only hiding.

Officers, Supervisors, and System Administrators see the full names and
the findings content. The task list and detail querysets are NOT
role-filtered for task metadata (single-ward pilot, no ward/cluster
scoping documented).

Out of scope: Priority 1 (D-01/P-01/D-12/D-13/D-14 — covered by
test_phase_d_priority1.py), Priority 3 (task workflow-state — D-08/D-09/
D-11), Priority 4 (audit quality — D-04/D-05/D-06/D-07/D-10/P-08).
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_task_with_owner(owner, status="assigned"):
    """Create a FollowUpTask with an approved advisory and a named owner."""
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
    """Create a FieldFinding on a task."""
    from apps.tasks.models import FieldFinding

    return FieldFinding.objects.create(
        task=task,
        visit_date=visit_date,
        observations="Test observation text",
        missing_information="",
        submitted_by=submitted_by,
    )


# ---------------------------------------------------------------------------
# D-02: Viewer name redaction on the task list
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_task_list_viewer_sees_tasks_but_names_redacted(viewer_client, officer):
    """A Viewer can access /tasks/ (read-only per about page) but officer
    names must be redacted to role labels per synthetic_data_notice.md:31.
    """
    task = _make_task_with_owner(officer)
    r = viewer_client.get("/tasks/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The task should be listed
    assert f"Task {task.id}" in html
    # The officer's real name must NOT appear
    assert officer.full_name not in html, (
        f"Viewer must not see officer real name '{officer.full_name}' in task list"
    )
    assert officer.username not in html, (
        "Viewer must not see officer username in task list"
    )
    # The role label should appear instead
    assert "Officer" in html, "Viewer should see 'Officer' role label, not the real name"


@pytest.mark.django_db
def test_task_list_officer_sees_full_names(officer_client, officer):
    """An officer can see the full owner display_name in the task list."""
    task = _make_task_with_owner(officer)
    r = officer_client.get("/tasks/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert f"Task {task.id}" in html
    assert officer.full_name in html, (
        f"Officer should see the full owner name '{officer.full_name}' in task list"
    )


@pytest.mark.django_db
def test_task_list_supervisor_sees_full_names(supervisor_client, officer):
    """A supervisor can see the full owner display_name in the task list."""
    task = _make_task_with_owner(officer)
    r = supervisor_client.get("/tasks/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert officer.full_name in html


@pytest.mark.django_db
def test_task_list_system_admin_sees_full_names(system_admin_client, officer):
    """A system admin can see the full owner display_name in the task list."""
    task = _make_task_with_owner(officer)
    r = system_admin_client.get("/tasks/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert officer.full_name in html


@pytest.mark.django_db
def test_task_list_anonymous_redirected_to_login():
    """Anonymous users are redirected to login (not 200 or 403)."""
    c = Client()
    r = c.get("/tasks/")
    assert r.status_code in {302, 301}
    assert "/accounts/login/" in r["Location"]


# ---------------------------------------------------------------------------
# D-02: Viewer name redaction on the task detail
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_task_detail_viewer_sees_task_but_names_redacted(viewer_client, officer, supervisor):
    """A Viewer can access /tasks/<pk>/ but officer names (owner,
    submitted_by, verified_by) must be redacted per synthetic_data_notice.
    """
    task = _make_task_with_owner(officer, status="completed")
    finding = _make_finding(task, submitted_by=officer)
    # Simulate supervisor verification
    finding.verified_by = supervisor
    finding.verified_at = "2026-10-15T12:00:00+00:00"
    finding.save(update_fields=["verified_by", "verified_at"])

    r = viewer_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The task should be accessible
    assert f"Task {task.id}" in html
    # Officer's real name must NOT appear anywhere
    assert officer.full_name not in html, (
        f"Viewer must not see officer real name '{officer.full_name}' in task detail"
    )
    assert officer.username not in html
    # Supervisor's real name must NOT appear
    assert supervisor.full_name not in html, (
        f"Viewer must not see supervisor real name '{supervisor.full_name}' in task detail"
    )
    assert supervisor.username not in html
    # The owner role label should appear (the task owner is redacted to "Officer")
    assert "Officer" in html
    # The "Supervisor" role label was previously rendered inside the
    # findings section ("Verified by Supervisor"). Since the D-02
    # correction hides the entire findings section for Viewers, the
    # "Supervisor" label is correctly absent from the Viewer response.
    # The supervisor identity is not exposed in any form.


@pytest.mark.django_db
def test_task_detail_officer_sees_full_names(officer_client, officer):
    """An officer can see the full owner display_name in the task detail."""
    task = _make_task_with_owner(officer)
    r = officer_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert officer.full_name in html


@pytest.mark.django_db
def test_task_detail_supervisor_sees_full_names(supervisor_client, officer):
    """A supervisor can see the full owner display_name in the task detail."""
    task = _make_task_with_owner(officer)
    r = supervisor_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert officer.full_name in html


@pytest.mark.django_db
def test_task_detail_system_admin_sees_full_names(system_admin_client, officer):
    """A system admin can see the full owner display_name in the task detail."""
    task = _make_task_with_owner(officer)
    r = system_admin_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert officer.full_name in html


@pytest.mark.django_db
def test_task_detail_anonymous_redirected_to_login(officer):
    """Anonymous users are redirected to login on task detail."""
    task = _make_task_with_owner(officer)
    c = Client()
    r = c.get(f"/tasks/{task.id}/")
    assert r.status_code in {302, 301}
    assert "/accounts/login/" in r["Location"]


# ---------------------------------------------------------------------------
# D-02: Direct URL access (enumeration protection for name leakage)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_viewer_cannot_enumerate_officer_names_via_task_detail(viewer_client, officer):
    """A Viewer accessing multiple task detail pages by ID must never see
    any officer's real name. This guards against name leakage via direct
    URL enumeration.
    """
    # Create tasks owned by different officers
    other_officer = User.objects.create(
        username="phase_d_other_officer_d02",
        role="extension_officer",
        full_name="Unique Other Name",
        sub_county="Nyatike",
        ward="Kachieng",
        is_active=True,
        approval_status="approved",
    )
    task1 = _make_task_with_owner(officer)
    task2 = _make_task_with_owner(other_officer)

    for task in [task1, task2]:
        r = viewer_client.get(f"/tasks/{task.id}/")
        assert r.status_code == 200
        html = r.content.decode("utf-8")
        assert officer.full_name not in html
        assert other_officer.full_name not in html


@pytest.mark.django_db
def test_task_detail_nonexistent_returns_404(viewer_client):
    """A nonexistent task ID returns 404 (not 200 or 403)."""
    r = viewer_client.get("/tasks/999999/")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# D-02 correction: Viewer must NOT see field-finding content (server-side)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_viewer_cannot_see_finding_observations(viewer_client, officer):
    """D-02 correction: a Viewer must NOT see the finding's observations
    text. The findings content is excluded from the Viewer's response
    server-side (empty ``findings`` context list, no ``field_findings``
    prefetch). The about page documents "read-only access to tasks" for
    Viewers, but the FieldFinding model is documented as "internal only"
    (apps/tasks/models.py:61), so findings content is restricted to
    officers and supervisors.
    """
    task = _make_task_with_owner(officer, status="in_progress")
    finding = _make_finding(task, submitted_by=officer)

    r = viewer_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The observation text must NOT be visible to a Viewer
    assert "Test observation text" not in html, (
        "Viewer must not see field-finding observations text"
    )
    # The submitter's real name must NOT appear
    assert officer.full_name not in html
    assert officer.username not in html
    # The "Submitted findings" section heading must NOT appear for Viewers
    assert "Submitted findings" not in html, (
        "Viewer must not see the 'Submitted findings' section heading"
    )


@pytest.mark.django_db
def test_viewer_cannot_see_missing_information_notes(viewer_client, officer):
    """D-02 correction: a Viewer must NOT see the finding's
    missing_information notes.
    """
    task = _make_task_with_owner(officer, status="in_progress")
    from apps.tasks.models import FieldFinding
    FieldFinding.objects.create(
        task=task,
        visit_date="2026-10-15",
        observations="Visible observations",
        missing_information="Secret missing info notes",
        submitted_by=officer,
    )
    r = viewer_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Secret missing info notes" not in html, (
        "Viewer must not see missing_information notes"
    )
    assert "Visible observations" not in html, (
        "Viewer must not see any findings content (observations included)"
    )


@pytest.mark.django_db
def test_viewer_cannot_see_follow_up_notes(viewer_client, officer):
    """D-02 correction: a Viewer must NOT see the finding's
    follow_up_notes. The template does not currently render follow_up_notes
    directly, but the field is in the model and must not be exposed via
    any template path. This test guards against a future template change
    that might render it.
    """
    task = _make_task_with_owner(officer, status="in_progress")
    from apps.tasks.models import FieldFinding
    FieldFinding.objects.create(
        task=task,
        visit_date="2026-10-15",
        observations="Some observation",
        missing_information="",
        follow_up_notes="Secret follow-up notes",
        submitted_by=officer,
    )
    r = viewer_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Secret follow-up notes" not in html, (
        "Viewer must not see follow_up_notes"
    )


@pytest.mark.django_db
def test_viewer_task_with_multiple_findings_exposes_none(viewer_client, officer):
    """D-02 correction: a Viewer accessing a task with multiple findings
    must not see ANY of the findings content. This guards against partial
    exposure when multiple findings exist.
    """
    task = _make_task_with_owner(officer, status="in_progress")
    _make_finding(task, submitted_by=officer, visit_date="2026-10-10")
    _make_finding(task, submitted_by=officer, visit_date="2026-10-12")
    _make_finding(task, submitted_by=officer, visit_date="2026-10-15")

    r = viewer_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # None of the findings content should appear
    assert "Test observation text" not in html
    assert "Submitted findings" not in html
    # The task metadata should still be visible
    assert f"Task {task.id}" in html


@pytest.mark.django_db
def test_viewer_task_with_no_findings_works_cleanly(viewer_client, officer):
    """D-02 correction: a Viewer accessing a task with no findings must
    see the task page without errors and without the "Submitted findings"
    section or the "No field findings yet" empty-state message.
    """
    task = _make_task_with_owner(officer, status="assigned")
    # No findings created
    r = viewer_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert f"Task {task.id}" in html
    assert "Submitted findings" not in html
    assert "No field findings yet" not in html


@pytest.mark.django_db
def test_officer_still_sees_findings_content(officer_client, officer):
    """D-02 correction regression: an officer must still see the full
    findings content (observations, submitter name) on the task detail.
    """
    task = _make_task_with_owner(officer, status="in_progress")
    finding = _make_finding(task, submitted_by=officer)

    r = officer_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Submitted findings" in html
    assert "Test observation text" in html, "Officer must see findings observations"
    assert officer.full_name in html, "Officer must see submitter full name"


@pytest.mark.django_db
def test_supervisor_still_sees_findings_content(supervisor_client, officer):
    """D-02 correction regression: a supervisor must still see the full
    findings content on the task detail.
    """
    task = _make_task_with_owner(officer, status="completed")
    finding = _make_finding(task, submitted_by=officer)

    r = supervisor_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Submitted findings" in html
    assert "Test observation text" in html
    assert officer.full_name in html


@pytest.mark.django_db
def test_direct_task_url_cannot_bypass_viewer_restriction(viewer_client, officer):
    """D-02 correction: a Viewer cannot bypass the findings restriction by
    directly accessing the task detail URL. The restriction is enforced
    server-side in the view's get_queryset/get_context_data, not in the
    template. Even if the Viewer knows the task ID, the findings content
    is absent from the response.
    """
    task = _make_task_with_owner(officer, status="in_progress")
    _make_finding(task, submitted_by=officer)

    # Direct URL access — no navigation, no referrer, direct GET
    r = viewer_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Test observation text" not in html
    assert "Submitted findings" not in html


# ---------------------------------------------------------------------------
# D-02: Regression — existing valid workflows still work
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_officer_can_still_submit_findings(officer_client, officer):
    """Regression: an officer can still submit findings on a task.
    The D-02 changes (context flag + template redaction) must not break
    the findings submission workflow.
    """
    from apps.tasks.models import FieldFinding

    task = _make_task_with_owner(officer, status="assigned")
    r = officer_client.post(
        f"/tasks/{task.id}/findings/",
        {
            "visit_date": "2026-10-15",
            "observations": "D-02 regression test observation",
            "missing_information": "",
        },
    )
    assert r.status_code == 302
    assert FieldFinding.objects.filter(task=task).count() == 1


@pytest.mark.django_db
def test_existing_task_detail_ui_tests_still_pass(officer_client):
    """Regression: the existing Step 3 UI tests (form action, button,
    input IDs) still pass with the D-02 context changes.
    """
    from tests.factories.models import AdvisoryFactory
    from apps.tasks.models import FollowUpTask

    a = AdvisoryFactory(status="approved")
    task = FollowUpTask.objects.create(
        approved_advisory=a, task_type="field_visit", status="assigned",
    )
    r = officer_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert f'action="/tasks/{task.id}/findings/"' in html
    assert "Save findings" in html
    assert "min-h-[44px]" in html
    assert 'id="id_visit_date"' in html
    assert 'id="id_observations"' in html
    assert 'id="id_missing_information"' in html


# ---------------------------------------------------------------------------
# D-02: Unassigned task (owner=None) handling for Viewers
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_task_list_viewer_sees_unassigned_label(viewer_client):
    """A Viewer sees 'Unassigned' for tasks with no owner (same as officers).
    The redaction only applies to named owners.
    """
    from tests.factories.models import AdvisoryFactory
    from apps.tasks.models import FollowUpTask

    a = AdvisoryFactory(status="approved")
    task = FollowUpTask.objects.create(
        approved_advisory=a, task_type="field_visit", status="assigned",
        owner=None,
    )
    r = viewer_client.get("/tasks/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert f"Task {task.id}" in html
    assert "Unassigned" in html


@pytest.mark.django_db
def test_task_detail_viewer_sees_unassigned_label(viewer_client):
    """A Viewer sees 'Unassigned' for a task with no owner on the detail page."""
    from tests.factories.models import AdvisoryFactory
    from apps.tasks.models import FollowUpTask

    a = AdvisoryFactory(status="approved")
    task = FollowUpTask.objects.create(
        approved_advisory=a, task_type="field_visit", status="assigned",
        owner=None,
    )
    r = viewer_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Unassigned" in html
