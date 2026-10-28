import uuid

import pytest
from django.urls import reverse

from apps.advisories.models import Advisory
from apps.tasks.models import FieldFinding, FollowUpTask
from tests.factories.models import AdvisoryFactory


def make_task(officer, status=FollowUpTask.Status.ASSIGNED):
    advisory = AdvisoryFactory()
    return FollowUpTask.objects.create(
        approved_advisory=advisory,
        owner=officer,
        task_type=FollowUpTask.TaskType.FIELD_VISIT,
        status=status,
    )


def sync_payload(task, client_id=None):
    return {
        "records": [
            {
                "client_id": str(client_id or uuid.uuid4()),
                "task_id": task.pk,
                "visit_date": "2026-10-28",
                "observations": "Offline field observation",
                "missing_information": "",
                "follow_up_notes": "",
                "checklist": {
                    "onset_verified_locally": True,
                    "pest_scouting_done": False,
                },
            }
        ]
    }


@pytest.mark.django_db
def test_officer_can_sync_finding_and_start_assigned_task(officer_client, officer):
    task = make_task(officer)

    response = officer_client.post(
        reverse("tasks:sync_field_findings"),
        data=sync_payload(task),
        content_type="application/json",
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "synced"
    assert result["duplicate"] is False

    finding = FieldFinding.objects.get(task=task)
    assert finding.submitted_by == officer
    assert finding.checklist["onset_verified_locally"] is True

    task.refresh_from_db()
    assert task.status == FollowUpTask.Status.IN_PROGRESS


@pytest.mark.django_db
def test_retrying_same_client_id_does_not_create_duplicate(officer_client, officer):
    task = make_task(officer)
    client_id = uuid.uuid4()
    payload = sync_payload(task, client_id)

    first = officer_client.post(
        reverse("tasks:sync_field_findings"),
        data=payload,
        content_type="application/json",
    )
    second = officer_client.post(
        reverse("tasks:sync_field_findings"),
        data=payload,
        content_type="application/json",
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["results"][0]["status"] == "synced"
    assert second.json()["results"][0]["duplicate"] is True
    assert FieldFinding.objects.filter(client_id=client_id).count() == 1


@pytest.mark.django_db
def test_viewer_cannot_sync_findings(viewer_client, officer):
    task = make_task(officer)

    response = viewer_client.post(
        reverse("tasks:sync_field_findings"),
        data=sync_payload(task),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert not FieldFinding.objects.filter(task=task).exists()


@pytest.mark.django_db
def test_completed_task_rejects_new_finding(officer_client, officer):
    task = make_task(officer, FollowUpTask.Status.COMPLETED)

    response = officer_client.post(
        reverse("tasks:sync_field_findings"),
        data=sync_payload(task),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "rejected"
    assert not FieldFinding.objects.filter(task=task).exists()


@pytest.mark.django_db
def test_invalid_json_is_rejected(officer_client):
    response = officer_client.post(
        reverse("tasks:sync_field_findings"),
        data="{not valid json",
        content_type="application/json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_sync_rejects_non_json_content_type(officer_client):
    response = officer_client.post(
        reverse("tasks:sync_field_findings"),
        data="records=empty",
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status_code == 415
