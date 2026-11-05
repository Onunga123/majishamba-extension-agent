"""Generate a scoped, expiring API token bound to an officer account.

The raw token is printed exactly once and must be stored immediately; only
its SHA-256 hash is persisted.

Example::

    python manage.py generate_api_token \\
        --user officer1 \\
        --name "Base44 production" \\
        --scopes advisories:request approvals:record token:introspect token:revoke \\
        --days 90
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.api.models import ApiToken

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Generate a scoped, expiring API token bound to an officer account. "
        "The raw token is printed once and must be stored immediately."
    )

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="Username the token is bound to.")
        parser.add_argument("--name", required=True, help="Human label for the token.")
        parser.add_argument(
            "--scopes",
            nargs="+",
            required=True,
            choices=[s.value for s in ApiToken.Scope],
            help="Scopes to grant (space-separated).",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Token expiry in days (default 90). Pass 0 for no expiry.",
        )

    def handle(self, *args, **options):
        username = options["user"]
        try:
            user = User.objects.get_by_natural_key(username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' does not exist.")
        if not user.is_officer():
            raise CommandError(
                f"User '{username}' is not an active officer; "
                "tokens must bind to an eligible officer account."
            )

        days = options["days"]
        expires_at = None if days == 0 else timezone.now() + timedelta(days=days)
        _token, raw = ApiToken.create_token(
            user=user,
            name=options["name"],
            scopes=options["scopes"],
            created_by=user,
            expires_at=expires_at,
        )
        self.stdout.write(
            self.style.SUCCESS(
                "API token created. Store this raw token now — it will not be shown again."
            )
        )
        self.stdout.write(raw)
