#!/usr/bin/env python
"""Smoke test: run the agent pipeline end-to-end for KACH-01.
Used by the build to confirm the system actually works.

Requires a real officer account to exist. Create one with:

    python manage.py create_officer --username smoke_officer --full-name "Smoke Test" --role extension_officer
    python manage.py changepassword smoke_officer

Or set SMOKE_OFFICER_USERNAME to use a different existing account.
"""
from __future__ import annotations

import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from apps.accounts.models import User
from apps.advisories.models import Advisory
from apps.agents.runner import run_advisory_pipeline
from apps.audit.models import AuditEvent


def main() -> int:
    username = os.environ.get("SMOKE_OFFICER_USERNAME", "smoke_officer")
    try:
        officer = User.objects.get(username=username)
    except User.DoesNotExist:
        print(f"FAILED — user {username!r} does not exist.")
        print(f"  Create one with:")
        print(f"    python manage.py create_officer --username {username} --full-name 'Smoke Test' --role extension_officer")
        print(f"    python manage.py changepassword {username}")
        return 2
    result = run_advisory_pipeline(
        cluster_id="KACH-01", ward="Kachieng", sub_county="Nyatike", county="Migori", actor=officer,
    )
    print("Agent result:", result)
    if not result.get("advisory_id"):
        print("FAILED — no advisory produced.")
        return 1
    adv = Advisory.objects.get(id=result["advisory_id"])
    print(f"OK — advisory #{adv.id} status={adv.status} mode={adv.generation_mode}")
    print(f"   recommendation={adv.recommendation_type}")
    print(f"   evidence_count={adv.evidence.count()}")
    print(f"   audit_events={AuditEvent.objects.count()}")
    # Approve and create a follow-up task
    from apps.approvals.models import OfficerApproval
    OfficerApproval.objects.create(advisory=adv, officer=officer, decision="approved", comments="Smoke test approval")
    adv.status = Advisory.Status.APPROVED
    adv.save()
    from apps.tasks.service import create_follow_up_task_after_approval
    res = create_follow_up_task_after_approval(
        approved_advisory_id=adv.id, officer_id=officer.id,
        task_type="field_visit", deadline="2025-11-15", ward="Kachieng", actor=officer,
    )
    print("Task creation:", res)
    return 0 if res.get("task_id") else 1


if __name__ == "__main__":
    sys.exit(main())
