"""API token model for external integrations (e.g. a Base44-built app).

Tokens are persisted only as SHA-256 hashes; the raw token is returned to the
caller exactly once, at creation time. Each token is:

* scoped  — a explicit list of Scope values, checked per request
* expiring — an optional ``expires_at``; null means "does not expire"
* revocable — ``revoked_at`` disables a token immediately, without deletion
* bound to a User — the officer whose authority the token carries. The bound
  user's eligibility is re-checked on every authenticated request, so a token
  whose officer is later suspended or demoted stops working at once.
"""

from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of a raw token string."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class ApiToken(models.Model):
    """A scoped, expiring, revocable API token bound to an officer account."""

    class Scope(models.TextChoices):
        ADVISORIES_REQUEST = "advisories:request", "Request advisory runs"
        ADVISORIES_READ = "advisories:read", "Read advisory runs and drafts"
        APPROVALS_RECORD = "approvals:record", "Record officer approvals"
        TOKEN_INTROSPECT = "token:introspect", "Introspect own token"
        TOKEN_REVOKE = "token:revoke", "Revoke own token"

    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    name = models.CharField(
        max_length=120,
        help_text="Human label, e.g. 'Base44 production'.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_tokens",
        help_text="Officer whose authority this token carries. Eligibility is re-checked per request.",
    )
    scopes = models.JSONField(
        default=list,
        blank=True,
        help_text="List of Scope values granted to this token.",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Null = does not expire. Set an expiry in production.",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="api_tokens_created",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "revoked_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"ApiToken '{self.name}' ({self.user})"

    # --- Lifecycle -----------------------------------------------------------
    @property
    def is_active(self) -> bool:
        """True if not revoked and not past expiry.

        Does NOT check the bound user's eligibility — that is the auth
        decorator's job, because it depends on the requested scope.
        """
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= timezone.now():
            return False
        return True

    def has_scope(self, scope: str) -> bool:
        return scope in (self.scopes or [])

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])

    def touch(self) -> None:
        """Update last_used_at via an UPDATE, avoiding a full model save."""
        ApiToken.objects.filter(pk=self.pk).update(last_used_at=timezone.now())

    # --- Creation ------------------------------------------------------------
    @classmethod
    def create_token(
        cls,
        *,
        user,
        name: str,
        scopes,
        created_by=None,
        expires_at=None,
    ) -> tuple[ApiToken, str]:
        """Create a token and return ``(token, raw_token)``.

        The raw token is shown only here; only its hash is persisted.
        """
        prefix = settings.MAJISHAMBA.get("API_TOKEN_NAME_PREFIX", "majishamba_")
        raw = prefix + secrets.token_urlsafe(32)
        token = cls.objects.create(
            token_hash=hash_token(raw),
            name=name,
            user=user,
            scopes=list(scopes),
            expires_at=expires_at,
            created_by=created_by or user,
        )
        return token, raw
