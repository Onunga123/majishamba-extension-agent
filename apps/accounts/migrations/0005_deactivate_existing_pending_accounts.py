"""Deactivate existing pending accounts that have is_active=True.

Before Phase A, registration set approval_status='pending' but did NOT
set is_active=False (Django's default). This left pending accounts able
to authenticate via Django's ModelBackend (which checks is_active).

This migration retroactively deactivates those existing pending accounts
by setting is_active=False, matching the new RegistrationForm.save()
behaviour. It is idempotent and safe to run multiple times — it only
affects accounts where approval_status='pending' AND is_active=True.

Accounts with approval_status='approved' are NOT touched.
Accounts with approval_status='rejected' or 'suspended' are NOT touched
(they should already have is_active=False from the rejection flow).

This migration is IRREVERSIBLE. The reverse callable is omitted from
RunPython so Django raises an IrreversibleError if anyone attempts to
roll it back. This prevents accidental reactivation of unapproved
pending accounts, which would restore the security vulnerability that
Phase A was designed to fix.
"""
from __future__ import annotations

from django.db import migrations


def deactivate_pending_accounts(apps, schema_editor):
    """Set is_active=False on all pending accounts that are still active."""
    User = apps.get_model("accounts", "User")
    User.objects.filter(
        approval_status="pending",
        is_active=True,
    ).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_user_rejected_at_user_rejected_by_and_more"),
    ]

    operations = [
        migrations.RunPython(
            deactivate_pending_accounts,
        ),
    ]
