import json
import uuid

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.audit.service import log_audit_event
from .forms import FieldFindingForm
from .models import FieldFinding, FollowUpTask


@login_required
@require_POST
def field_findings_sync(request):
    if not request.user.is_officer():
        return JsonResponse({"error": "Officer access required."}, status=403)

    if request.content_type != "application/json":
        return JsonResponse({"error": "Expected application/json."}, status=415)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records or len(records) > 20:
        return JsonResponse(
            {"error": "Send between 1 and 20 records."}, status=400
        )

    results = []

    for item in records:
        if not isinstance(item, dict):
            results.append({"client_id": None, "status": "rejected",
                            "error": "Record must be an object."})
            continue

        raw_id = item.get("client_id")
        try:
            client_id = uuid.UUID(str(raw_id))
            task_id = int(item.get("task_id"))
        except (ValueError, TypeError, AttributeError):
            results.append({"client_id": raw_id, "status": "rejected",
                            "error": "Valid client_id and task_id are required."})
            continue

        try:
            with transaction.atomic():
                existing = FieldFinding.objects.filter(
                    client_id=client_id
                ).first()

                if existing:
                    if (
                        existing.task_id == task_id
                        and existing.submitted_by_id == request.user.pk
                    ):
                        results.append({
                            "client_id": str(client_id),
                            "status": "synced",
                            "duplicate": True,
                        })
                    else:
                        results.append({
                            "client_id": str(client_id),
                            "status": "conflict",
                            "error": "This client ID is already associated with another record.",
                        })
                    continue

                task = (
                    FollowUpTask.objects.select_for_update()
                    .filter(pk=task_id)
                    .first()
                )

                if task is None:
                    results.append({
                        "client_id": str(client_id),
                        "status": "rejected",
                        "error": "Task not found.",
                    })
                    continue

                if task.status not in {
                    FollowUpTask.Status.ASSIGNED,
                    FollowUpTask.Status.IN_PROGRESS,
                }:
                    results.append({
                        "client_id": str(client_id),
                        "status": "rejected",
                        "error": "Task is not accepting field findings.",
                    })
                    continue

                form = FieldFindingForm({
                    "visit_date": item.get("visit_date", ""),
                    "observations": item.get("observations", ""),
                    "missing_information": item.get("missing_information", ""),
                    "follow_up_notes": item.get("follow_up_notes", ""),
                })

                if not form.is_valid():
                    results.append({
                        "client_id": str(client_id),
                        "status": "rejected",
                        "errors": form.errors.get_json_data(),
                    })
                    continue

                finding = form.save(commit=False)
                finding.client_id = client_id
                finding.task = task
                finding.submitted_by = request.user

                checklist = item.get("checklist", {})
                if not isinstance(checklist, dict):
                    results.append({
                        "client_id": str(client_id),
                        "status": "rejected",
                        "error": "Checklist must be an object.",
                    })
                    continue

                finding.checklist = {
                    "onset_verified_locally":
                        checklist.get("onset_verified_locally") is True,
                    "pest_scouting_done":
                        checklist.get("pest_scouting_done") is True,
                }

                previous_status = task.status
                finding.save()

                if task.status == FollowUpTask.Status.ASSIGNED:
                    task.status = FollowUpTask.Status.IN_PROGRESS
                    task.save(update_fields=["status"])

                log_audit_event(
                    actor=request.user,
                    action="task:finding",
                    target=task,
                    metadata={
                        "task_id": task.pk,
                        "finding_id": finding.pk,
                        "client_id": str(client_id),
                        "previous_status": previous_status,
                        "transitioned_to": task.status,
                        "source": "offline_sync",
                    },
                )

            results.append({
                "client_id": str(client_id),
                "status": "synced",
                "duplicate": False,
            })

        except IntegrityError:
            existing = FieldFinding.objects.filter(
                client_id=client_id
            ).first()

            if (
                existing
                and existing.task_id == task_id
                and existing.submitted_by_id == request.user.pk
            ):
                results.append({
                    "client_id": str(client_id),
                    "status": "synced",
                    "duplicate": True,
                })
            else:
                results.append({
                    "client_id": str(client_id),
                    "status": "conflict",
                    "error": "Could not safely confirm this record. Retry later.",
                })

    return JsonResponse({"results": results})
