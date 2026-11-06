"""Domain service for requesting advisory runs.

Extracted from ``apps.advisories.views.RequestAdvisoryView`` so that both the
server-rendered web view and the public API trigger a run through one code
path. The service owns the 30-minute dedup window (an officer re-requesting
the same cluster within the window reuses the in-flight run rather than
spawning a duplicate) and the async kick-off.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.permissions import require_officer
from apps.agents.models import AdvisoryRun
from apps.agents.run_worker import start_advisory_run_async
from apps.clusters.models import FarmerCluster

# A run in any of these statuses is considered "in flight": re-requesting the
# same officer+cluster within the dedup window reuses it instead of duplicating.
_INFLIGHT_STATUSES = [
    AdvisoryRun.Status.QUEUED,
    AdvisoryRun.Status.RUNNING,
    AdvisoryRun.Status.WAITING_FOR_MODEL,
    AdvisoryRun.Status.VALIDATING,
]

_DEDUP_WINDOW = timedelta(minutes=30)


class AdvisoryRequestError(Exception):
    """Base class for advisory-request service errors."""


class ClusterNotFound(AdvisoryRequestError):
    """No FarmerCluster matches the supplied cluster_id."""


@dataclass(frozen=True)
class AdvisoryRequestResult:
    run_id: str
    status: str
    created: bool


@transaction.atomic
def request_advisory_run(*, actor, cluster_id: str) -> AdvisoryRequestResult:
    """Create (or reuse) an advisory run for ``actor`` on ``cluster_id``.

    Raises ``PermissionDenied`` if the actor is not an officer, and
    ``ClusterNotFound`` if no cluster matches. Returns the run id;
    ``created=False`` means a recent in-flight run was reused.

    The dedup check, run creation, and async dispatch run inside a
    ``transaction.atomic`` block, and the cluster row is locked with
    ``select_for_update`` so two concurrent requests for the same cluster
    cannot both pass the "no in-flight run" check and create duplicate runs
    (the TOCTOU the roadmap flags for this phase). On SQLite (dev) the row
    lock is a no-op; on Postgres (production) it is a real row lock.
    """
    require_officer(actor)
    try:
        cluster = FarmerCluster.objects.select_for_update().get(cluster_id=cluster_id)
    except FarmerCluster.DoesNotExist as exc:
        raise ClusterNotFound(f"No cluster with cluster_id '{cluster_id}'.") from exc

    cutoff = timezone.now() - _DEDUP_WINDOW
    existing = (
        AdvisoryRun.objects.filter(
            requested_by=actor,
            cluster=cluster,
            status__in=_INFLIGHT_STATUSES,
            created_at__gte=cutoff,
        )
        .order_by("-created_at")
        .first()
    )
    if existing is not None:
        return AdvisoryRequestResult(
            run_id=str(existing.run_id),
            status=existing.status,
            created=False,
        )

    run = AdvisoryRun.objects.create(
        requested_by=actor,
        cluster=cluster,
        status=AdvisoryRun.Status.QUEUED,
        current_message="Queued — starting shortly",
    )
    transaction.on_commit(lambda: start_advisory_run_async(run.pk))
    return AdvisoryRequestResult(run_id=str(run.run_id), status=run.status, created=True)
