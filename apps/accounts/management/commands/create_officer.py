"""Management command to create a real officer account for production.

Usage:
    python manage.py create_officer --username jdoe --full-name "John Doe" --role extension_officer
    python manage.py create_officer --username jsmith --full-name "Jane Smith" --role supervisor

The password is NOT set by this command — use `python manage.py changepassword <username>`
to set it interactively after creation. This prevents passwords from appearing in
command-line history or logs.

Phase D (P-01): ``is_staff`` is no longer set to ``True`` unconditionally.
The application role (extension_officer/supervisor/viewer) is the source of
truth for authorization. Django admin access (``is_staff=True``) is a separate
privilege that should be granted explicitly via the Django admin UI if needed —
not automatically by this provisioning command. The previous unconditional
``is_staff=True`` caused a Viewer provisioned via ``--role viewer`` to pass
``is_staff``-based authorization checks (now fixed in D-01), and was inconsistent
with ``create_system_admin`` which sets ``is_staff=False``.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a real officer/supervisor/viewer account for production. Password must be set separately via changepassword."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="Login username (e.g. jdoe)")
        parser.add_argument("--full-name", required=True, help="Real name of the officer (e.g. 'John Doe')")
        parser.add_argument("--role", choices=["extension_officer", "supervisor", "viewer"], default="extension_officer",
                          help="Role: extension_officer (can request + approve), supervisor (can approve), viewer (read-only)")
        parser.add_argument("--sub-county", default="Nyatike", help="Sub-county assignment (default: Nyatike)")
        parser.add_argument("--ward", default="Kachieng", help="Ward assignment (default: Kachieng)")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        full_name = options["full_name"]
        role = options["role"]
        sub_county = options["sub_county"]
        ward = options["ward"]

        if User.objects.filter(username=username).exists():
            raise CommandError(f"User '{username}' already exists.")

        user = User.objects.create(
            username=username,
            role=role,
            full_name=full_name,
            sub_county=sub_county,
            ward=ward,
            is_staff=False,
            is_superuser=False,
        )
        # Set an unusable password — officer must set it via `changepassword`
        user.set_unusable_password()
        user.save()

        self.stdout.write(self.style.SUCCESS(
            f"Created {role} account: {username} ({full_name}), {sub_county}, {ward}."
        ))
        self.stdout.write("")
        self.stdout.write("IMPORTANT: Set the password now:")
        self.stdout.write(f"  python manage.py changepassword {username}")
        self.stdout.write("")
        self.stdout.write("The account is active but has no password — login will fail until you set one.")
        self.stdout.write("")
        self.stdout.write("NOTE: Django admin access (is_staff) is NOT granted by this command.")
        self.stdout.write("      If the account needs Django admin access, grant it explicitly via")
        self.stdout.write("      /admin/auth/user/ in the Django admin UI.")
