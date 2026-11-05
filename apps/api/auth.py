"""Token authentication decorator for the public API.

The decorator is ``csrf_exempt`` — API clients (e.g. a Base44 app) cannot use
Django's session CSRF cookie. It authenticates a request via an
``Authorization: Bearer <token>`` header (an ``X-API-Key`` header is accepted
as a fallback), looks up the ``ApiToken`` by its SHA-256 hash, and re-checks
the bound user's eligibility on every request. Re-checking eligibility is the
load-bearing safety property: a token whose officer is later suspended,
demoted, or had their approval revoked stops working immediately, without
anyone having to revoke the token itself.
"""

from __future__ import annotations

import functools
import logging

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import ApiToken, hash_token

logger = logging.getLogger("majishamba.api")

# Each scope maps to the eligibility check the bound user must STILL pass.
# This is independent of the token's own validity: even a non-expired,
# non-revoked token is rejected if the officer it belongs to no longer
# qualifies for the scope's action.
_SCOPE_ELIGIBILITY = {
    ApiToken.Scope.ADVISORIES_REQUEST: lambda user: user.is_officer(),
    ApiToken.Scope.ADVISORIES_READ: lambda user: user.is_officer() or user.is_system_admin(),
    ApiToken.Scope.APPROVALS_RECORD: lambda user: user.can_approve(),
    ApiToken.Scope.TOKEN_INTROSPECT: lambda user: bool(user.is_active),
    ApiToken.Scope.TOKEN_REVOKE: lambda user: bool(user.is_active),
}


def _error(status: int, code: str, message: str, **extra) -> JsonResponse:
    payload = {"error": {"code": code, "message": message}}
    payload["error"].update(extra)
    return JsonResponse(payload, status=status)


def _extract_bearer_token(request) -> str | None:
    header = request.META.get("HTTP_AUTHORIZATION", "") or ""
    if header.startswith("Bearer "):
        return header[len("Bearer ") :].strip() or None
    # Some clients prefer a dedicated header.
    return (request.META.get("HTTP_X_API_KEY", "") or "").strip() or None


def token_required(scope: str):
    """Require a valid, unexpired, unrevoked ApiToken with ``scope``.

    The bound user must also still satisfy the scope's eligibility check.
    On success, ``request.user`` is set to the bound officer and
    ``request.api_token`` to the token.
    """

    def decorator(view_func):
        @csrf_exempt
        @functools.wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            raw = _extract_bearer_token(request)
            if not raw:
                return _error(
                    401, "missing_token", "Authorization: Bearer <token> header required."
                )

            token = (
                ApiToken.objects.select_related("user").filter(token_hash=hash_token(raw)).first()
            )
            if token is None:
                return _error(401, "invalid_token", "Token not recognized.")

            if token.revoked_at is not None:
                return _error(403, "token_revoked", "This token has been revoked.")
            if token.expires_at is not None and token.expires_at <= timezone.now():
                return _error(403, "token_expired", "This token has expired.")

            user = token.user
            if not (user and user.is_active):
                return _error(
                    403, "user_inactive", "The account bound to this token is not active."
                )

            eligible = _SCOPE_ELIGIBILITY.get(scope)
            if eligible is None or not eligible(user):
                return _error(
                    403,
                    "not_eligible",
                    "The account bound to this token no longer satisfies the required role.",
                )
            if not token.has_scope(scope):
                return _error(403, "insufficient_scope", f"Token lacks scope '{scope}'.")

            request.user = user
            request.api_token = token
            token.touch()
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
