"""Background execution for advisory runs."""
from __future__ import annotations

import logging
import threading
from typing import Any

from django.db import close_old_connections
from django.utils import timezone

from apps.agents.models import AdvisoryRun
from apps.agents.runner import run_advisory_pipeline
from apps.clusters.models import FarmerCluster

logger = logging.getLogger("majishamba.run_worker")


def execute_advisory_run(run_pk: int) -> None:
    close_old_connections()
    run = AdvisoryRun.objects.select_related("cluster", "requested_by").get(pk=run_pk)
    cluster = run.cluster
    run.status = AdvisoryRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])

    result: dict[str, Any] = run_advisory_pipeline(
        cluster_id=cluster.cluster_id,
        ward=cluster.ward.name,
        sub_county=cluster.ward.sub_county.name,
        county=cluster.ward.sub_county.county.name,
        actor=run.requested_by,
        advisory_run_id=run.pk,
    )
    run.refresh_from_db()
    mode = result.get("generation_mode") or ""
    if result.get("advisory_id"):
        from apps.advisories.models import Advisory

        adv = Advisory.objects.get(pk=result["advisory_id"])
        run.result_advisory = adv
        run.generation_mode = adv.generation_mode
        run.pipeline_request_id = result.get("request_id") or ""
        if adv.generation_mode == "fallback_template":
            run.status = AdvisoryRun.Status.COMPLETED_WITH_FALLBACK
        else:
            run.status = AdvisoryRun.Status.COMPLETED
        run.current_message = "Draft ready for officer review"
        run.error_message = ""
    else:
        run.status = AdvisoryRun.Status.FAILED
        run.error_message = (result.get("error") or "Advisory run failed.")[:500]
        run.current_message = "Run failed — see message below"
    run.finished_at = timezone.now()
    run.save(
        update_fields=[
            "status",
            "result_advisory",
            "generation_mode",
            "pipeline_request_id",
            "current_message",
            "error_message",
            "finished_at",
        ]
    )


def start_advisory_run_async(run_pk: int) -> None:
    """Start pipeline in a daemon thread (demo-friendly when RQ worker is not running)."""
    import os

    if os.environ.get("MAJISHAMBA_SYNC_RUN") == "1":
        execute_advisory_run(run_pk)
        return
    thread = threading.Thread(target=execute_advisory_run, args=(run_pk,), daemon=True)
    thread.start()
    logger.info("Started advisory run thread for pk=%s", run_pk)
