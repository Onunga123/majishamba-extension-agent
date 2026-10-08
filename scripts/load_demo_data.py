#!/usr/bin/env python
"""scripts/load_demo_data.py — TEST/DEVELOPMENT ONLY. Not for production.

This script previously seeded three named synthetic demo accounts
(``nyatike_officer``, ``nyatike_supervisor``, ``nyatike_viewer``) with a
shared password. Those accounts have been removed to keep the login
experience minimal and professional — see README and the
``cleanup_demo_accounts`` management command for the full story.

What this script does now:
    * Nothing destructive. It is a no-op for the synthetic demo accounts.
    * It still prints a short message documenting the recommended way to
      create a *real* officer account in development: via the
      ``create_officer`` management command (which never sets a password
      from the command line).

Why keep the file at all?
    * The Makefile ``fixtures`` target and ``scripts/run_demo.sh`` /
      ``scripts/run_demo.ps1`` reference it. Removing it would break
      those entry points. Keeping it as a no-op preserves backward
      compatibility for existing developers without reintroducing the
      synthetic demo accounts.

If you want to create a real officer for local testing:

    python manage.py create_officer \\
        --username jdoe \\
        --full-name "John Doe" \\
        --role extension_officer \\
        --sub-county Nyatike \\
        --ward Kachieng
    python manage.py changepassword jdoe

That creates a real, auditable account whose password is set
interactively (not stored in scripts or fixtures).

If you have an existing deployment that still has the old synthetic
demo accounts and you want to remove them safely, run:

    python manage.py cleanup_demo_accounts --dry-run      # list only
    python manage.py cleanup_demo_accounts --confirm      # actually deactivate
    python manage.py cleanup_demo_accounts --confirm --delete  # hard delete

The ``--delete`` mode preserves audit history by default (the AuditEvent
model uses ``on_delete=SET_NULL`` for its ``actor`` FK, so deleting a
user keeps the audit event with a NULL actor rather than cascading).
"""
from __future__ import annotations

import sys


def main() -> int:
    print("==> scripts/load_demo_data.py — TEST/DEVELOPMENT ONLY")
    print("    This script no longer seeds synthetic demo accounts.")
    print("    To create a real officer for local testing, run:")
    print("        python manage.py create_officer \\")
    print("            --username jdoe --full-name 'John Doe' \\")
    print("            --role extension_officer --sub-county Nyatike --ward Kachieng")
    print("        python manage.py changepassword jdoe")
    print("")
    print("    To remove any leftover synthetic demo accounts from an old deploy, run:")
    print("        python manage.py cleanup_demo_accounts --dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
