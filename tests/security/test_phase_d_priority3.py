"""Phase D Priority 3 regression tests — task workflow-state enforcement.

Covers the approved Priority 3 findings:

D-08: TaskVerifyView now requires COMPLETED status and at least one
      field finding before verification. Invalid source states
      (ASSIGNED, IN_PROGRESS, VERIFIED, CLOSED, CANCELLED) and tasks
      with no findings are rejected with 403. The existing
      ``is_superuser`` exception and self-verification restriction are
      preserved.

D-09: TaskCompleteView now requires ASSIGNED or IN_PROGRESS status
      before completion. Completing from COMPLETED, VERIFIED, CLOSED,
      or CANCELLED is rejected with 403.

D-11: TaskFieldFindingView now requires ASSIGNED or IN_PROGRESS status
      before finding submission. Submitting findings on COMPLETED,
      VERIFIED, CLOSED, or CANCELLED tasks is rejected with 403.

R-1:  Both TaskFieldFindingView and TaskCompleteView now require
      ``request.user.is_officer()`` — task ownership alone is no longer
      sufficient. A Viewer or System Administrator who owns a task
      (via an abnormal path) is rejected.

Approved workflow: ASSIGNED → IN_PROGRESS → COMPLETED → VERIFIED.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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
    """Create a FieldFinding on a task."""
    from apps.tasks.models import FieldFinding

    return FieldFinding.objects.create(
        task=task,
        visit_date=visit_date,
        observations="Priority 3 test observation",
        missing_information="",
        submitted_by=submitted_by,
    )


# ---------------------------------------------------------------------------
# D-09: Task completion state preconditions
# ---------------------------------------------------------------------------
class TestTaskCompletion:
    @pytest.mark.django_db
    def test_complete_from_assigned_succeeds(self, officer_client, officer):
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="assigned")
        r = officer_client.post(f"/tasks/{task.id}/complete/")
        assert r.status_code == 302
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.COMPLETED

    @pytest.mark.django_db
    def test_complete_from_in_progress_succeeds(self, officer_client, officer):
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="in_progress")
        r = officer_client.post(f"/tasks/{task.id}/complete/")
        assert r.status_code == 302
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.COMPLETED

    @pytest.mark.django_db
    def test_complete_from_completed_rejected(self, officer_client, officer):
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="completed")
        r = officer_client.post(f"/tasks/{task.id}/complete/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.COMPLETED

    @pytest.mark.django_db
    def test_complete_from_verified_rejected(self, officer_client, officer):
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="verified")
        r = officer_client.post(f"/tasks/{task.id}/complete/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.VERIFIED

    @pytest.mark.django_db
    def test_complete_from_closed_rejected(self, officer_client, officer):
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="closed")
        r = officer_client.post(f"/tasks/{task.id}/complete/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.CLOSED

    @pytest.mark.django_db
    def test_complete_from_cancelled_rejected(self, officer_client, officer):
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="cancelled")
        r = officer_client.post(f"/tasks/{task.id}/complete/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.CANCELLED


# ---------------------------------------------------------------------------
# D-08: Task verification state + findings preconditions
# ---------------------------------------------------------------------------
class TestTaskVerification:
    @pytest.mark.django_db
    def test_verify_completed_task_with_finding_succeeds(self, supervisor_client, officer):
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="completed")
        _make_finding(task, submitted_by=officer)
        r = supervisor_client.post(f"/tasks/{task.id}/verify/")
        assert r.status_code == 302
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.VERIFIED

    @pytest.mark.django_db
    def test_verify_assigned_task_rejected(self, supervisor_client, officer):
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="assigned")
        _make_finding(task, submitted_by=officer)
        r = supervisor_client.post(f"/tasks/{task.id}/verify/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.ASSIGNED

    @pytest.mark.django_db
    def test_verify_in_progress_task_rejected(self, supervisor_client, officer):
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="in_progress")
        _make_finding(task, submitted_by=officer)
        r = supervisor_client.post(f"/tasks/{task.id}/verify/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.IN_PROGRESS

    @pytest.mark.django_db
    def test_verify_verified_task_rejected(self, supervisor_client, officer):
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="verified")
        _make_finding(task, submitted_by=officer)
        r = supervisor_client.post(f"/tasks/{task.id}/verify/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.VERIFIED

    @pytest.mark.django_db
    def test_verify_closed_task_rejected(self, supervisor_client, officer):
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="closed")
        _make_finding(task, submitted_by=officer)
        r = supervisor_client.post(f"/tasks/{task.id}/verify/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.CLOSED

    @pytest.mark.django_db
    def test_verify_cancelled_task_rejected(self, supervisor_client, officer):
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="cancelled")
        _make_finding(task, submitted_by=officer)
        r = supervisor_client.post(f"/tasks/{task.id}/verify/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.CANCELLED

    @pytest.mark.django_db
    def test_verify_completed_task_without_findings_rejected(self, supervisor_client, officer):
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="completed")
        # No findings created
        r = supervisor_client.post(f"/tasks/{task.id}/verify/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.COMPLETED

    @pytest.mark.django_db
    def test_verify_preserves_finding_metadata_on_rejection(self, supervisor_client, officer):
        """A rejected verification must not change finding verified_by/verified_at."""
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="assigned")  # wrong state
        finding = _make_finding(task, submitted_by=officer)
        assert finding.verified_by is None
        assert finding.verified_at is None
        r = supervisor_client.post(f"/tasks/{task.id}/verify/")
        assert r.status_code == 403
        finding.refresh_from_db()
        assert finding.verified_by is None
        assert finding.verified_at is None

    @pytest.mark.django_db
    def test_self_verification_still_blocked(self, supervisor_client, supervisor):
        """The existing self-verification restriction is preserved."""
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=supervisor, status="completed")
        _make_finding(task, submitted_by=supervisor)
        r = supervisor_client.post(f"/tasks/{task.id}/verify/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.COMPLETED

    @pytest.mark.django_db
    def test_is_superuser_bypass_preserved(self, officer):
        """The existing is_superuser exception in TaskVerifyView is preserved
        per the approved policy (P-07 deferred). A superuser can verify
        even without the SUPERVISOR role."""
        from apps.tasks.models import FollowUpTask
        from apps.accounts.models import User

        # Create a user with is_superuser=True but role != SUPERVISOR
        superuser = User.objects.create(
            username="phase_d_p3_super",
            role="extension_officer",
            full_name="Superuser",
            sub_county="Nyatike",
            ward="Kachieng",
            is_active=True,
            approval_status="approved",
            is_staff=True,
            is_superuser=True,
        )
        task = _make_task(owner=officer, status="completed")
        _make_finding(task, submitted_by=officer)
        c = Client()
        c.force_login(superuser)
        r = c.post(f"/tasks/{task.id}/verify/")
        assert r.status_code == 302
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.VERIFIED


# ---------------------------------------------------------------------------
# D-11: Field-finding submission state preconditions
# ---------------------------------------------------------------------------
class TestFindingSubmission:
    @pytest.mark.django_db
    def test_submit_findings_from_assigned_succeeds(self, officer_client, officer):
        from apps.tasks.models import FollowUpTask, FieldFinding

        task = _make_task(owner=officer, status="assigned")
        r = officer_client.post(
            f"/tasks/{task.id}/findings/",
            {"visit_date": "2026-10-15", "observations": "Test", "missing_information": ""},
        )
        assert r.status_code == 302
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.IN_PROGRESS
        assert FieldFinding.objects.filter(task=task).count() == 1

    @pytest.mark.django_db
    def test_submit_findings_from_in_progress_succeeds(self, officer_client, officer):
        from apps.tasks.models import FollowUpTask, FieldFinding

        task = _make_task(owner=officer, status="in_progress")
        r = officer_client.post(
            f"/tasks/{task.id}/findings/",
            {"visit_date": "2026-10-15", "observations": "Test", "missing_information": ""},
        )
        assert r.status_code == 302
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.IN_PROGRESS
        assert FieldFinding.objects.filter(task=task).count() == 1

    @pytest.mark.django_db
    def test_submit_findings_from_completed_rejected(self, officer_client, officer):
        from apps.tasks.models import FollowUpTask, FieldFinding

        task = _make_task(owner=officer, status="completed")
        r = officer_client.post(
            f"/tasks/{task.id}/findings/",
            {"visit_date": "2026-10-15", "observations": "Test", "missing_information": ""},
        )
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.COMPLETED
        assert FieldFinding.objects.filter(task=task).count() == 0

    @pytest.mark.django_db
    def test_submit_findings_from_verified_rejected(self, officer_client, officer):
        from apps.tasks.models import FollowUpTask, FieldFinding

        task = _make_task(owner=officer, status="verified")
        r = officer_client.post(
            f"/tasks/{task.id}/findings/",
            {"visit_date": "2026-10-15", "observations": "Test", "missing_information": ""},
        )
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.VERIFIED
        assert FieldFinding.objects.filter(task=task).count() == 0

    @pytest.mark.django_db
    def test_submit_findings_from_closed_rejected(self, officer_client, officer):
        from apps.tasks.models import FollowUpTask, FieldFinding

        task = _make_task(owner=officer, status="closed")
        r = officer_client.post(
            f"/tasks/{task.id}/findings/",
            {"visit_date": "2026-10-15", "observations": "Test", "missing_information": ""},
        )
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.CLOSED
        assert FieldFinding.objects.filter(task=task).count() == 0

    @pytest.mark.django_db
    def test_submit_findings_from_cancelled_rejected(self, officer_client, officer):
        from apps.tasks.models import FollowUpTask, FieldFinding

        task = _make_task(owner=officer, status="cancelled")
        r = officer_client.post(
            f"/tasks/{task.id}/findings/",
            {"visit_date": "2026-10-15", "observations": "Test", "missing_information": ""},
        )
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.CANCELLED
        assert FieldFinding.objects.filter(task=task).count() == 0

    @pytest.mark.django_db
    def test_invalid_form_does_not_persist_finding(self, officer_client, officer):
        """An invalid form submission (missing visit_date) on a valid-state
        task must re-render with errors (200) but not create a finding."""
        from apps.tasks.models import FieldFinding

        task = _make_task(owner=officer, status="assigned")
        r = officer_client.post(
            f"/tasks/{task.id}/findings/",
            {"observations": "Missing visit_date", "missing_information": ""},
        )
        assert r.status_code == 200
        assert FieldFinding.objects.filter(task=task).count() == 0


# ---------------------------------------------------------------------------
# R-1: Owner-only authorization bypass removed
# ---------------------------------------------------------------------------
class TestRoleEnforcement:
    @pytest.mark.django_db
    def test_viewer_who_owns_task_cannot_submit_findings(self, viewer):
        """R-1: A Viewer who owns a task (abnormal state) must NOT be able
        to submit findings. Only officers/supervisors may submit findings."""
        from apps.tasks.models import FieldFinding

        task = _make_task(owner=viewer, status="assigned")
        c = Client()
        c.force_login(viewer)
        r = c.post(
            f"/tasks/{task.id}/findings/",
            {"visit_date": "2026-10-15", "observations": "Viewer attempt", "missing_information": ""},
        )
        assert r.status_code == 403
        assert FieldFinding.objects.filter(task=task).count() == 0

    @pytest.mark.django_db
    def test_viewer_who_owns_task_cannot_complete(self, viewer):
        """R-1: A Viewer who owns a task (abnormal state) must NOT be able
        to complete it. Only officers/supervisors may complete tasks."""
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=viewer, status="assigned")
        c = Client()
        c.force_login(viewer)
        r = c.post(f"/tasks/{task.id}/complete/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.ASSIGNED

    @pytest.mark.django_db
    def test_system_admin_who_owns_task_cannot_submit_findings(self, system_admin):
        """R-1: A System Administrator who owns a task (abnormal state) must
        NOT be able to submit findings. Only officers/supervisors may submit."""
        from apps.tasks.models import FieldFinding

        task = _make_task(owner=system_admin, status="assigned")
        c = Client()
        c.force_login(system_admin)
        r = c.post(
            f"/tasks/{task.id}/findings/",
            {"visit_date": "2026-10-15", "observations": "Admin attempt", "missing_information": ""},
        )
        assert r.status_code == 403
        assert FieldFinding.objects.filter(task=task).count() == 0

    @pytest.mark.django_db
    def test_system_admin_who_owns_task_cannot_complete(self, system_admin):
        """R-1: A System Administrator who owns a task (abnormal state) must
        NOT be able to complete it. Only officers/supervisors may complete."""
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=system_admin, status="assigned")
        c = Client()
        c.force_login(system_admin)
        r = c.post(f"/tasks/{task.id}/complete/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.ASSIGNED

    @pytest.mark.django_db
    def test_officer_not_owner_can_submit_findings(self, officer_client, officer, supervisor):
        """An officer who does NOT own the task can still submit findings
        via is_officer() — this is the existing intended behavior."""
        from apps.tasks.models import FieldFinding

        task = _make_task(owner=supervisor, status="assigned")
        r = officer_client.post(
            f"/tasks/{task.id}/findings/",
            {"visit_date": "2026-10-15", "observations": "Non-owner officer", "missing_information": ""},
        )
        assert r.status_code == 302
        assert FieldFinding.objects.filter(task=task).count() == 1

    @pytest.mark.django_db
    def test_officer_not_owner_can_complete(self, officer_client, supervisor):
        """An officer who does NOT own the task can still complete it
        via is_officer() — this is the existing intended behavior."""
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=supervisor, status="in_progress")
        r = officer_client.post(f"/tasks/{task.id}/complete/")
        assert r.status_code == 302
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.COMPLETED

    @pytest.mark.django_db
    def test_viewer_cannot_submit_findings_on_normal_task(self, viewer_client, officer):
        """A Viewer is denied findings submission on a normally-owned task."""
        from apps.tasks.models import FieldFinding

        task = _make_task(owner=officer, status="assigned")
        r = viewer_client.post(
            f"/tasks/{task.id}/findings/",
            {"visit_date": "2026-10-15", "observations": "Viewer attempt", "missing_information": ""},
        )
        assert r.status_code == 403
        assert FieldFinding.objects.filter(task=task).count() == 0

    @pytest.mark.django_db
    def test_viewer_cannot_complete_normal_task(self, viewer_client, officer):
        """A Viewer is denied task completion on a normally-owned task."""
        from apps.tasks.models import FollowUpTask

        task = _make_task(owner=officer, status="assigned")
        r = viewer_client.post(f"/tasks/{task.id}/complete/")
        assert r.status_code == 403
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.ASSIGNED


# ---------------------------------------------------------------------------
# Regression: valid full workflow still works end-to-end
# ---------------------------------------------------------------------------
class TestFullWorkflow:
    @pytest.mark.django_db
    def test_full_workflow_assigned_to_verified(self, officer_client, supervisor_client, officer, supervisor):
        """The full approved workflow ASSIGNED → IN_PROGRESS → COMPLETED → VERIFIED
        works end-to-end for authorized roles."""
        from apps.tasks.models import FollowUpTask, FieldFinding

        # 1. ASSIGNED → submit findings → IN_PROGRESS
        task = _make_task(owner=officer, status="assigned")
        r = officer_client.post(
            f"/tasks/{task.id}/findings/",
            {"visit_date": "2026-10-15", "observations": "Field visit done", "missing_information": ""},
        )
        assert r.status_code == 302
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.IN_PROGRESS
        assert FieldFinding.objects.filter(task=task).count() == 1

        # 2. IN_PROGRESS → complete → COMPLETED
        r = officer_client.post(f"/tasks/{task.id}/complete/")
        assert r.status_code == 302
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.COMPLETED

        # 3. COMPLETED → verify → VERIFIED
        r = supervisor_client.post(f"/tasks/{task.id}/verify/")
        assert r.status_code == 302
        task.refresh_from_db()
        assert task.status == FollowUpTask.Status.VERIFIED

        # 4. Verify the finding was stamped
        finding = task.field_findings.first()
        assert finding.verified_by == supervisor
        assert finding.verified_at is not None
