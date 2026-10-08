"""Management command to safely identify, deactivate, or delete leftover
synthetic demo accounts (``nyatike_officer``, ``nyatike_supervisor``,
``nyatike_viewer``) and optionally any account whose name still matches a
demo pattern.

The command is **read-only by default** — running it without flags just
lists what it would do. Pass ``--confirm`` to apply changes. Pass
``--delete`` (with ``--confirm``) to hard-delete instead of deactivating.

Audit history is preserved because the ``AuditEvent.actor`` FK uses
``on_delete=SET_NULL``: deleting a user leaves the audit row behind with
a NULL ``actor`` rather than cascading the delete.

Usage:
    python manage.py cleanup_demo_accounts                 # list only
    python manage.py cleanup_demo_accounts --dry-run       # list only (explicit)
    python manage.py cleanup_demo_accounts --confirm       # deactivate
    python manage.py cleanup_demo_accounts --confirm --delete  # hard delete
    python manage.py cleanup_demo_accounts --usernames nyatike_officer --dry-run
    python manage.py cleanup_demo_accounts --include-pattern --dry-run

Safety:
    * Without --confirm, the command NEVER modifies the database.
    * With --confirm, the default action is DEACTIVATE (set is_active=False).
      This is reversible — set is_active=True again to restore.
    * With --confirm --delete, the user rows are deleted. Audit rows
      referencing them are preserved (actor becomes NULL).
    * The command refuses to delete users that don't match the demo
      username list or pattern unless --usernames is used to name them
      explicitly (so you can't accidentally delete real accounts).
"""
from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


# Default set of synthetic demo usernames that older deploys may still have.
# These names are also referenced in README's "Cleanup" section so operators
# know exactly what this command targets.
DEFAULT_DEMO_USERNAMES: tuple[str, ...] = (
    "nyatike_officer",
    "nyatike_supervisor",
    "nyatike_viewer",
)

# Regex that matches demo-flavoured usernames. Conservative — only matches
# names that contain 'demo' or 'synthetic' OR start with 'nyatike_'.
# Used only when --include-pattern is passed.
DEMO_USERNAME_PATTERN = re.compile(r"(nyatike_|demo|synthetic)", re.IGNORECASE)


class Command(BaseCommand):
    help = (
        "Safely list, deactivate, or delete leftover synthetic demo accounts. "
        "Read-only by default; pass --confirm to apply changes. Audit history "
        "is preserved (AuditEvent.actor uses on_delete=SET_NULL)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--usernames",
            nargs="+",
            default=list(DEFAULT_DEMO_USERNAMES),
            help=(
                "Specific usernames to target (default: the three synthetic "
                "demo accounts). Pass custom usernames only if you know what "
                "you are doing."
            ),
        )
        parser.add_argument(
            "--include-pattern",
            action="store_true",
            default=False,
            help=(
                "Also target any user whose username matches the demo pattern "
                "(nyatike_*, *demo*, *synthetic*). Use with care — can match "
                "more than the three default names."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="List what would happen but make no DB changes (this is the default).",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            default=False,
            help="Actually apply the action. Without this flag the command is read-only.",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            default=False,
            help=(
                "Hard-delete the matched users instead of deactivating them. "
                "Requires --confirm. Audit rows are preserved (FK is SET_NULL)."
            ),
        )
        parser.add_argument(
            "--preserve-audit",
            action="store_true",
            default=True,
            help=(
                "Always preserve audit history (default behavior — this flag "
                "is kept for forward-compat; the AuditEvent.actor FK is "
                "SET_NULL at the model level so audit rows are never cascaded)."
            ),
        )

    def handle(self, *args, **options):
        User = get_user_model()

        usernames: list[str] = list(options["usernames"])
        include_pattern: bool = options["include_pattern"]
        dry_run: bool = options["dry_run"]
        confirm: bool = options["confirm"]
        delete: bool = options["delete"]

        if dry_run and confirm:
            raise CommandError("Pass either --dry-run or --confirm, not both.")

        if delete and not confirm:
            raise CommandError("--delete requires --confirm (refusing to delete without explicit confirmation).")

        # Build the queryset of users to target
        qs = User.objects.none()
        if usernames:
            qs = qs | User.objects.filter(username__in=usernames)
        if include_pattern:
            # Filter by regex — Django's regex lookup is case-sensitive by default,
            # so we use iregex for case-insensitive matching.
            qs = qs | User.objects.filter(username__iregex=r"nyatike_|demo|synthetic")

        # De-duplicate
        matched_ids: set[int] = set()
        users_to_process = []
        for u in qs:
            if u.id in matched_ids:
                continue
            matched_ids.add(u.id)
            users_to_process.append(u)

        if not users_to_process:
            self.stdout.write(self.style.SUCCESS(
                "No matching demo accounts found. Nothing to do."
            ))
            return

        # Count audit events linked to these users so we can show that
        # the audit history is preserved regardless of action.
        from apps.audit.models import AuditEvent
        audit_counts: dict[int, int] = {}
        for u in users_to_process:
            audit_counts[u.id] = AuditEvent.objects.filter(actor=u).count()

        # Header
        self.stdout.write("")
        self.stdout.write(self.style.WARNING(
            f"Found {len(users_to_process)} matching account(s):"
        ))
        self.stdout.write("")
        for u in users_to_process:
            self.stdout.write(
                f"  id={u.id:<6} username={u.username:<30} role={u.role:<20} "
                f"is_active={u.is_active} audit_events={audit_counts[u.id]}"
            )
        self.stdout.write("")

        if dry_run or not confirm:
            self.stdout.write(self.style.WARNING(
                "DRY RUN — no changes made. Pass --confirm to apply."
            ))
            if delete:
                self.stdout.write(self.style.WARNING(
                    "Action would be: HARD DELETE (audit rows preserved via SET_NULL FK)."
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    "Action would be: DEACTIVATE (set is_active=False). Reversible."
                ))
            return

        # Apply
        if delete:
            # Hard delete. Audit rows are preserved because AuditEvent.actor is SET_NULL.
            for u in users_to_process:
                uname = u.username
                uid = u.id
                u.delete()
                self.stdout.write(self.style.SUCCESS(
                    f"  DELETED user id={uid} username={uname!r} "
                    f"(audit rows preserved — actor FK is SET_NULL)"
                ))
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(
                f"Done. {len(users_to_process)} user(s) deleted. Audit history preserved."
            ))
        else:
            # Deactivate (reversible)
            for u in users_to_process:
                u.is_active = False
                u.save(update_fields=["is_active"])
                self.stdout.write(self.style.SUCCESS(
                    f"  DEACTIVATED user id={u.id} username={u.username!r} "
                    f"(reversible: set is_active=True to restore)"
                ))
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(
                f"Done. {len(users_to_process)} user(s) deactivated. Audit history untouched."
            ))
