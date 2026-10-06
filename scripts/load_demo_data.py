#!/usr/bin/env python
"""scripts/load_demo_data.py — seeds the named Nyatike extension officer + demo users.

Run after `make fixtures`. Safe to run multiple times (uses get_or_create).

NOTE: Passwords are only set on FIRST creation (when get_or_create returns created=True).
Subsequent runs do NOT reset passwords — this respects the security rule
that the application should not reset account passwords on every start.
To reset a demo account password manually, use:
    python manage.py changepassword nyatike_officer
"""
from __future__ import annotations

import os
import sys

import django


DEMO_PASSWORD = "majishamba-demo-2025"  # demo only; documented in README


def _upsert_user(username: str, defaults: dict, password: str = DEMO_PASSWORD) -> str:
    """Create the user if missing; never overwrite an existing password."""
    from apps.accounts.models import User
    user, created = User.objects.get_or_create(username=username, defaults=defaults)
    if created:
        user.set_password(password)
        user.save()
        return "created"
    # Existing user — do NOT reset password.
    return "exists"


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    django.setup()

    officer_status = _upsert_user(
        "nyatike_officer",
        defaults={
            "role": "extension_officer",
            "full_name": "Jane Awuor (Synthetic — Nyatike Extension Officer)",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
            "is_staff": True,
        },
    )
    sup_status = _upsert_user(
        "nyatike_supervisor",
        defaults={
            "role": "supervisor",
            "full_name": "Supervisor (Synthetic — Nyatike Sub-County)",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
            "is_staff": True,
        },
    )
    viewer_status = _upsert_user(
        "nyatike_viewer",
        defaults={
            "role": "viewer",
            "full_name": "Viewer (Synthetic — read-only)",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
        },
    )

    print("==> Demo users ready:")
    print(f"    nyatike_officer    ({officer_status}) — extension_officer — can request + approve")
    print(f"    nyatike_supervisor ({sup_status})    — supervisor — can approve")
    print(f"    nyatike_viewer     ({viewer_status}) — viewer — read-only")
    print("")
    print("    Password for freshly-created demo accounts: majishamba-demo-2025")
    print("    (Existing accounts' passwords are NOT reset on re-run.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
