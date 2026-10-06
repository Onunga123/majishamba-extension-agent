"""Update AdvisoryRun rows during LangGraph execution."""
from __future__ import annotations

from django.utils import timezone

from .models import AdvisoryRun

STAGE_MESSAGES: dict[str, str] = {
    "validate_request": "Checking cluster request",
    "fetch_plot_history": "Checking plot records",
    "fetch_crop_calendar": "Reading maize guidance",
    "fetch_weather": "Retrieving weather evidence",
    "fetch_pest_alerts": "Checking pest alerts",
    "fetch_market_prices": "Reading market context",
    "validate_evidence": "Checking missing or conflicting information",
    "draft_advisory": "Preparing a draft",
    "validate_output_schema": "Validating evidence references",
    "save_draft": "Saving draft for officer review",
    "officer_approval_gate": "Draft ready for officer review",
}


def mark_run_stage(*, run_db_id: int | None, stage: str, status: str | None = None) -> None:
    if not run_db_id:
        return
    message = STAGE_MESSAGES.get(stage, stage.replace("_", " ").capitalize())
    try:
        run = AdvisoryRun.objects.get(pk=run_db_id)
    except AdvisoryRun.DoesNotExist:
        return
    stages = list(run.completed_stages or [])
    if message and message not in stages:
        stages.append(message)
    updates: dict = {
        "current_stage": stage,
        "current_message": message,
        "completed_stages": stages,
    }
    if status:
        updates["status"] = status
    if status == AdvisoryRun.Status.RUNNING and not run.started_at:
        updates["started_at"] = timezone.now()
    AdvisoryRun.objects.filter(pk=run_db_id).update(**updates)
