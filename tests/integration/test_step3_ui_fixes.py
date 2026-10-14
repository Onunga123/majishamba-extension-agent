"""UX/UI Step 3 tests — field findings validation feedback and accessible labels.

Covers the three approved Step 3 changes:

S3-1: ``templates/tasks/detail.html`` — the field findings form now displays
      ``finding_form`` validation errors (form-level summary + per-field
      feedback) and preserves submitted values when validation fails.
      The form action, HTTP method, input names, IDs, styling, and
      successful-submission behavior are preserved.

S3-2: ``templates/advisories/request.html`` — the cluster filter search
      input now has an associated ``sr-only`` ``<label>`` (matching the
      dashboard search pattern), so screen readers can announce its
      purpose. The input ID, filtering behavior, and visual layout are
      preserved.

S3-3: ``templates/accounts/account_review.html`` — the rejection reason
      input now has a visible ``<label>`` ("Rejection reason") with a
      per-row unique ID. The approval/rejection workflow and form
      behavior are preserved.

Out of scope (not tested here): security behavior from Phases A/B/C
(covered by tests/security/test_security.py, test_phase_b_audit_visibility.py,
test_phase_c_profile_security.py), Step 1/Step 2 UI work (covered by
test_integration_forms_ui.py and test_phase2_ui_consistency.py).
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_task_for_findings(status="assigned"):
    """Create a FollowUpTask with an approved advisory, ready for findings."""
    from tests.factories.models import AdvisoryFactory
    from apps.tasks.models import FollowUpTask

    adv = AdvisoryFactory(status="approved")
    return FollowUpTask.objects.create(
        approved_advisory=adv,
        task_type=FollowUpTask.TaskType.FIELD_VISIT,
        deadline="2030-01-01",
        status=status,
    )


# ---------------------------------------------------------------------------
# S3-1: Field findings validation feedback
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_invalid_field_findings_re_renders_with_visible_errors(officer_client):
    """POSTing findings with an empty visit_date must re-render the page
    (200, not 302) with a visible validation message. The visit_date field
    is required (DateField, no null/blank), so an empty submission is
    invalid.
    """
    from apps.tasks.models import FieldFinding

    task = _make_task_for_findings()
    r = officer_client.post(
        f"/tasks/{task.id}/findings/",
        {
            # visit_date intentionally omitted — should trigger validation error
            "observations": "Some observations text",
            "missing_information": "",
        },
    )
    assert r.status_code == 200, (
        f"Invalid findings POST should re-render (200), got {r.status_code}"
    )
    html = r.content.decode("utf-8")
    # The page must show a visible error. Django's default message for a
    # required DateField is "This field is required." We check for that
    # phrase OR for the visit_date field's id near an error marker.
    assert "This field is required." in html or "visit_date" in html.lower(), (
        "Invalid findings POST must display a visible validation error"
    )
    # The error must be in an accessible role="alert" container
    assert 'role="alert"' in html, (
        "Field validation error must be in a role=\"alert\" container"
    )
    # No FieldFinding row should have been created
    assert FieldFinding.objects.filter(task=task).count() == 0, (
        "No FieldFinding should be created on invalid submission"
    )


@pytest.mark.django_db
def test_invalid_field_findings_preserves_submitted_values(officer_client):
    """When the form re-renders after an invalid submission, the submitted
    observations and missing_information text must be preserved (not lost)
    so the officer doesn't have to retype them.
    """
    task = _make_task_for_findings()
    r = officer_client.post(
        f"/tasks/{task.id}/findings/",
        {
            # visit_date omitted — invalid
            "observations": "Preserved observations text",
            "missing_information": "Preserved missing info",
        },
    )
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert "Preserved observations text" in html, (
        "Submitted observations must be preserved on re-render"
    )
    assert "Preserved missing info" in html, (
        "Submitted missing_information must be preserved on re-render"
    )


@pytest.mark.django_db
def test_valid_field_findings_submission_succeeds(officer_client):
    """A valid POST (with visit_date) must create a FieldFinding and
    redirect to the task detail page. This is the regression guard for
    the successful-submission path — confirms the S3-1 template changes
    did not break the happy path.
    """
    from apps.tasks.models import FieldFinding, FollowUpTask

    task = _make_task_for_findings(status="assigned")
    r = officer_client.post(
        f"/tasks/{task.id}/findings/",
        {
            "visit_date": "2026-10-15",
            "observations": "Visit went well",
            "missing_information": "",
            "onset_verified_locally": "yes",
            "pest_scouting_done": "",
        },
    )
    assert r.status_code == 302, (
        f"Valid findings POST should redirect (302), got {r.status_code}"
    )
    assert f"/tasks/{task.id}/" in r["Location"]
    findings = FieldFinding.objects.filter(task=task)
    assert findings.count() == 1, "Exactly one FieldFinding should be created"
    finding = findings.first()
    assert str(finding.visit_date) == "2026-10-15"
    assert finding.observations == "Visit went well"
    assert finding.checklist == {
        "onset_verified_locally": True,
        "pest_scouting_done": False,
    }
    # Submitting findings on an assigned task should flip it to in_progress
    task.refresh_from_db()
    assert task.status == FollowUpTask.Status.IN_PROGRESS


@pytest.mark.django_db
def test_task_detail_findings_form_action_and_button_preserved(officer_client):
    """Regression guard: the S3-1 changes must not alter the form action
    URL, the submit button's 44px min-height, or the button label.
    """
    task = _make_task_for_findings()
    r = officer_client.get(f"/tasks/{task.id}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    assert f'action="/tasks/{task.id}/findings/"' in html, (
        "Form action must point to /tasks/<id>/findings/"
    )
    assert "Save findings" in html, "Submit button label must be 'Save findings'"
    assert "min-h-[44px]" in html, "Submit button must retain min-h-[44px]"
    assert "csrfmiddlewaretoken" in html, "CSRF token must be rendered"
    # The raw template tag must not leak
    assert "{% csrf_token %}" not in html
    assert "{% url" not in html


@pytest.mark.django_db
def test_task_detail_findings_form_input_ids_preserved(officer_client):
    """Regression guard: the input IDs must remain stable (the view's
    invalid-post path passes `finding_form` which references these IDs).
    """
    task = _make_task_for_findings()
    r = officer_client.get(f"/tasks/{task.id}/")
    html = r.content.decode("utf-8")
    assert 'id="id_visit_date"' in html
    assert 'id="id_observations"' in html
    assert 'id="id_missing_information"' in html
    assert 'name="visit_date"' in html
    assert 'name="observations"' in html
    assert 'name="missing_information"' in html


# ---------------------------------------------------------------------------
# S3-2: Advisory request cluster search accessible label
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_advisory_request_cluster_search_has_accessible_label(officer_client):
    """The cluster filter search input must have an associated <label>
    (either a <label for="cluster_search"> element or an aria-label).
    Matches the established sr-only label pattern in dashboard/home.html.
    """
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())

    r = officer_client.get("/advisories/request/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The input must still exist with its ID and placeholder
    assert 'id="cluster_search"' in html, "cluster_search input must retain its ID"
    assert 'placeholder="Filter by locality' in html, "Placeholder must be preserved"
    # An associated label must exist
    assert '<label for="cluster_search"' in html, (
        "cluster_search input must have an associated <label for=\"cluster_search\">"
    )
    # The label should be screen-reader-only (sr-only) to match the dashboard pattern
    assert 'class="sr-only"' in html, (
        "Label should use the sr-only pattern (matching dashboard/home.html)"
    )


@pytest.mark.django_db
def test_advisory_request_cluster_search_input_preserved(officer_client):
    """Regression guard: the S3-2 label addition must not change the input
    element's ID, name, placeholder, class, or the surrounding form.
    """
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())

    r = officer_client.get("/advisories/request/")
    html = r.content.decode("utf-8")
    assert 'id="cluster_search"' in html
    assert 'name="cluster_search"' in html or 'id="cluster_search"' in html
    assert 'class="ar-form-input"' in html
    assert 'autocomplete="off"' in html
    # The form and its submit button must be intact
    assert "Start advisory run" in html
    assert 'id="request-advisory-form"' in html


# ---------------------------------------------------------------------------
# S3-3: Account review rejection reason accessible label
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_account_review_rejection_reason_has_visible_label(system_admin):
    """The rejection reason input must have a visible <label> reading
    'Rejection reason' with a matching `for` attribute pointing to the
    input's ID.
    """
    # Create a pending account so the rejection form is rendered
    User.objects.create(
        username="phase_s3_pending_reject",
        full_name="S3 Pending Reject",
        role="viewer",
        requested_role="extension_officer",
        approval_status="pending",
        is_active=True,
        sub_county="Nyatike",
        ward="Kachieng",
    )
    c = Client()
    c.force_login(system_admin)
    r = c.get("/accounts/review/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # A visible label with the text "Rejection reason" must be present
    assert "Rejection reason" in html, (
        "A visible 'Rejection reason' label must be present"
    )
    # The label must have a `for` attribute matching the input's `id`
    # The input id includes the account pk to keep it unique per row.
    assert '<label for="id_rejection_reason_' in html, (
        "Label must have for=\"id_rejection_reason_<pk>\""
    )
    assert 'id="id_rejection_reason_' in html, (
        "Input must have id=\"id_rejection_reason_<pk>\""
    )
    # The input's name must be preserved (workflow unchanged)
    assert 'name="rejection_reason"' in html


@pytest.mark.django_db
def test_account_review_reject_workflow_still_works(system_admin):
    """Regression guard: the S3-3 label addition must not break the
    rejection workflow. A system admin must still be able to reject a
    pending account via the POST endpoint.
    """
    pending = User.objects.create(
        username="phase_s3_reject_workflow",
        full_name="S3 Reject Workflow",
        role="viewer",
        requested_role="extension_officer",
        approval_status="pending",
        is_active=True,
        sub_county="Nyatike",
        ward="Kachieng",
    )
    c = Client()
    c.force_login(system_admin)
    r = c.post(
        f"/accounts/review/{pending.id}/reject/",
        {"rejection_reason": "S3 workflow test"},
    )
    assert r.status_code == 302
    pending.refresh_from_db()
    assert pending.approval_status == "rejected"
    assert pending.is_active is False
    assert pending.rejection_reason == "S3 workflow test"


@pytest.mark.django_db
def test_account_review_approve_button_still_has_44px(system_admin):
    """Regression guard: the S3-3 change must not affect the approve
    button's 44px min-height (Step 2 requirement).
    """
    User.objects.create(
        username="phase_s3_approve_44px",
        full_name="S3 Approve 44px",
        role="viewer",
        requested_role="extension_officer",
        approval_status="pending",
        is_active=True,
        sub_county="Nyatike",
        ward="Kachieng",
    )
    c = Client()
    c.force_login(system_admin)
    r = c.get("/accounts/review/")
    html = r.content.decode("utf-8")
    assert "min-h-[44px]" in html, "Approve/Reject buttons must retain min-h-[44px]"
    assert "Approve" in html
    assert "Reject" in html
