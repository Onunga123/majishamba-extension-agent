"""Audit log service — centralised writer + middleware hook."""
from __future__ import annotations

import json
import logging
from typing import Any

from django.db import models
from django.utils.timezone import now

from .models import AuditEvent

logger = logging.getLogger("majishamba.audit")


def _model_name(obj: Any) -> tuple[str, str]:
    if obj is None:
        return "", ""
    if isinstance(obj, models.Model):
        return obj.__class__.__name__, str(obj.pk)
    return obj.__class__.__name__, ""


def _summarise(value: Any, max_len: int = 800) -> Any:
    """Sanitise and shorten values for the audit log."""
    try:
        if isinstance(value, (dict, list)):
            text = json.dumps(value, default=str, ensure_ascii=False)
        else:
            text = str(value)
        if len(text) > max_len:
            text = text[:max_len] + "…[truncated]"
        # No secrets — strip anything that looks like a token.
        for marker in ("password", "secret", "token", "api_key"):
            if marker in text.lower():
                idx = text.lower().find(marker)
                text = text[: idx] + f"<{marker} redacted>…"
        return text
    except Exception:  # pragma: no cover
        return "<unserializable>"


def log_audit_event(
    *,
    actor: Any = None,
    action: str,
    target: Any = None,
    metadata: dict[str, Any] | None = None,
    tool_name: str = "",
    inputs_summary: Any = None,
    outputs_summary: Any = None,
    approval_status: str = "",
) -> AuditEvent:
    """Write a single AuditEvent row + structured log line.

    Always succeeds (failures only log); never raises to the caller.
    """
    target_type, target_id = _model_name(target)
    actor_id = getattr(actor, "id", None) if actor else None
    try:
        event = AuditEvent.objects.create(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata=metadata or {},
            tool_name=tool_name,
            inputs_summary={"value": _summarise(inputs_summary)},
            outputs_summary={"value": _summarise(outputs_summary)},
            approval_status=approval_status,
        )
    except Exception as exc:  # pragma: no cover - audit must never break the call
        logger.exception("Failed to write audit event: %s", exc)
        return AuditEvent(action=action)

    logger.info(
        "audit.event",
        extra={
            "action": action,
            "actor_id": actor_id,
            "tool": tool_name,
            "target_type": target_type,
            "target_id": target_id,
            "approval": approval_status,
        },
    )
    return event


def log_tool_call(
    *,
    tool_name: str,
    inputs: dict[str, Any],
    outputs: Any,
    actor: Any = None,
    approval_status: str = "",
) -> AuditEvent:
    """Helper for MCP tools to log every call."""
    return log_audit_event(
        actor=actor,
        action=f"tool_call:{tool_name}",
        target=None,
        tool_name=tool_name,
        inputs_summary=inputs,
        outputs_summary=outputs,
        approval_status=approval_status,
        metadata={"ts": now().isoformat()},
    )
