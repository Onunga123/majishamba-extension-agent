"""Middleware to revalidate account eligibility on every authenticated request.

If an account has been deactivated (is_active=False) or has lost its
approved status (approval_status != 'approved') since the session was
created, the session is flushed and the user is redirected to the login
page. This prevents users from retaining access after:
  - An admin rejects their pending account
  - An admin suspends their account (future feature)
  - Any other process that sets is_active=False or approval_status to
    a non-approved value

The middleware runs AFTER AuthenticationMiddleware so request.user is
populated. It skips:
  - Anonymous requests (no user to check)
  - Requests to /accounts/login/ and /accounts/logout/ (so the user
    can be redirected there without being caught in a loop)
  - Requests to /accounts/register/ and /accounts/registration/pending/
    (public pages)
  - Static/media/health paths

NOTE: /admin/ is NOT exempt. A deactivated user must not be able to
continue accessing the Django admin interface through an existing session.
Django's admin has its own login page and authentication; if the user's
account has been deactivated, they will be kicked out by this middleware
and will need to re-authenticate (which will fail because is_active=False).
"""
from __future__ import annotations

from django.contrib.auth import logout
from django.shortcuts import redirect

# Paths exempt from the session-eligibility check.
_EXEMPT_PATHS = frozenset({
    "/accounts/login/",
    "/accounts/logout/",
    "/accounts/register/",
    "/accounts/registration/pending/",
})

_EXEMPT_PREFIXES = (
    "/static/",
    "/media/",
    "/health/",
)


class AccountStatusMiddleware:
    """Flush the session if the authenticated user is no longer eligible."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if user is not None and user.is_authenticated:
            path = request.path
            if path not in _EXEMPT_PATHS and not path.startswith(_EXEMPT_PREFIXES):
                # Re-check eligibility on every authenticated request.
                # Django's ModelBackend.get_user() already rejects is_active=False
                # users by returning None (making request.user = AnonymousUser),
                # so is_active is covered by Django's built-in mechanism.
                # Our middleware adds the approval_status check — if an admin
                # changes approval_status without also setting is_active=False,
                # the user's session is still invalidated here.
                if not user.is_approved():
                    # The account is no longer eligible — flush the session
                    # and redirect to login.
                    logout(request)
                    from django.conf import settings as dj_settings
                    return redirect(dj_settings.LOGIN_URL)

        return self.get_response(request)
