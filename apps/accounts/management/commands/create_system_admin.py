"""Create the initial approved System Administrator securely.

Usage::

    python manage.py create_system_admin --username admin --full-name "Name"

The password is collected interactively and is never accepted as a command-line
argument, which keeps it out of shell history and process listings.
"""
from __future__ import annotations

import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create an approved System Administrator; prompt securely for the password."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="Login username")
        parser.add_argument("--full-name", required=True, help="Administrator's real name")
        parser.add_argument("--email", default="", help="Optional administrator email")
        parser.add_argument("--sub-county", default="Nyatike", help="Sub-county assignment")
        parser.add_argument("--ward", default="Kachieng", help="Ward assignment")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        if User.objects.filter(username=username).exists():
            raise CommandError(f"User '{username}' already exists.")

        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Password (again): ")
        if not password:
            raise CommandError("Password cannot be empty.")
        if password != confirmation:
            raise CommandError("Passwords do not match.")

        user = User(
            username=username,
            full_name=options["full_name"],
            email=options["email"],
            sub_county=options["sub_county"],
            ward=options["ward"],
            role=User.Role.SYSTEM_ADMIN,
            requested_role=User.Role.SYSTEM_ADMIN,
            approval_status=User.ApprovalStatus.APPROVED,
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        user.set_password(password)
        user.save()

        self.stdout.write(self.style.SUCCESS(
            f"Created approved System Administrator account: {username}."
        ))
        self.stdout.write("Log in at /accounts/login/ with this username and the password you just set.")