#!/usr/bin/env python
"""scripts/load_demo_data.py — seeds the named Nyatike extension officer + demo users.

Run after `make fixtures`. Safe to run multiple times (uses get_or_create).
"""
from __future__ import annotations

import os
import sys

import django


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    django.setup()

    from apps.accounts.models import User

    # Named Nyatike extension officer — the human in the loop.
    officer, _ = User.objects.get_or_create(
        username="nyatike_officer",
        defaults={
            "role": User.Role.EXTENSION_OFFICER,
            "full_name": "Jane Awuor (Synthetic — Nyatike Extension Officer)",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
            "is_staff": True,
        },
    )
    officer.set_password("majishamba-demo-2025")
    officer.save()

    # Supervisor (can also approve)
    sup, _ = User.objects.get_or_create(
        username="nyatike_supervisor",
        defaults={
            "role": User.Role.SUPERVISOR,
            "full_name": "Supervisor (Synthetic — Nyatike Sub-County)",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
            "is_staff": True,
        },
    )
    sup.set_password("majishamba-demo-2025")
    sup.save()

    # Viewer (read-only)
    viewer, _ = User.objects.get_or_create(
        username="nyatike_viewer",
        defaults={
            "role": User.Role.VIEWER,
            "full_name": "Viewer (Synthetic — read-only)",
            "sub_county": "Nyatike",
            "ward": "Kachieng",
        },
    )
    viewer.set_password("majishamba-demo-2025")
    viewer.save()

    print("==> Demo users ready:")
    print("    nyatike_officer   / majishamba-demo-2025  (extension_officer)")
    print("    nyatike_supervisor/ majishamba-demo-2025  (supervisor)")
    print("    nyatike_viewer    / majishamba-demo-2025  (viewer)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
