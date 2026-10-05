"""High-level runner used by views to invoke the LangGraph agent."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from django.db import connection

from apps.audit.service import log_audit_event

from .graph import build_graph

logger = logging.getLogger("majishamba.runner")


def run_advisory_pipeline(
    *,
    cluster_id: str,
    ward: str = "Kachieng",
    sub_county: str = "Nyatike",
    county: str = "Migori",
    actor=None,
) -> dict[str, Any]:
    """Run the LangGraph agent for a Kachieng cluster request.

    Returns a dict with at least one of:
      - advisory_id (int): the new DRAFT Advisory record id, OR
      - error (str): a human-readable failure reason, OR
      - trace (list[str]): node trace for the request view.
    """
    request_id = str(uuid.uuid4())
    log_audit_event(
        actor=actor,
        action="agent_run:start",
        metadata={"cluster_id": cluster_id, "ward": ward, "request_id": request_id},
    )

    initial = {
        "cluster_id": cluster_id,
        "ward": ward,
        "sub_county": sub_county,
        "county": county,
        "actor_id": getattr(actor, "id", None),
        "request_id": request_id,
        "errors": [],
        "warnings": [],
    }

    try:
        graph = build_graph()
        # Some test/dev SQLite environments need a fresh connection for each request
        if connection.connection is None and connection.vendor == "sqlite":
            connection.connect()
        result = graph.invoke(initial)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover
        logger.exception("Agent run failed")
        log_audit_event(actor=actor, action="agent_run:failure", metadata={"cluster_id": cluster_id, "error": str(exc)})
        return {"error": f"Agent run failed: {exc}", "trace": []}

    advisory_id = result.get("advisory_id")
    errors = result.get("errors") or []
    warnings = result.get("warnings") or []

    log_audit_event(
        actor=actor,
        action="agent_run:end",
        metadata={
            "cluster_id": cluster_id,
            "request_id": request_id,
            "advisory_id": advisory_id,
            "errors": [str(e) for e in errors][:5],
            "warnings": warnings[:5],
            "generation_mode": result.get("generation_mode", "fallback_template"),
        },
    )

    if not advisory_id and errors:
        return {"error": errors[0].get("msg", "Unknown error"), "trace": warnings + [str(e) for e in errors]}
    if not advisory_id:
        return {"error": "Agent did not produce a DRAFT advisory.", "trace": warnings}
    return {"advisory_id": advisory_id, "trace": warnings, "generation_mode": result.get("generation_mode")}
