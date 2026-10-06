"""Views for the accounts app."""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy


# Capability summaries shown next to each demo account card.
# Roles are derived from the actual User.Role choices (apps.accounts.models)
# so the cards never describe a role that doesn't exist in the database.
_ROLE_CAPABILITIES = {
    "extension_officer": "Request advisories, review DRAFTs, approve or reject, create follow-up tasks.",
    "supervisor": "Approve or reject advisories; spot-check the audit trail. Cannot request advisories unless also an officer.",
    "viewer": "Read-only access to dashboard, advisories, tasks, audit. Cannot request or approve.",
}


def _demo_accounts() -> list[dict]:
    """Discover the actual seeded demo accounts and their roles.

    Only the three well-known demo usernames are surfaced. Real production
    user lists are never exposed regardless of DEMO_MODE.

    Returns a list of dicts: [{username, role, role_display, full_name, capabilities}, ...]
    Only accounts that actually exist in the database are returned.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    demo_usernames = ["nyatike_officer", "nyatike_supervisor", "nyatike_viewer"]
    # Order: officer first, then supervisor, then viewer — most capable first.
    out: list[dict] = []
    for username in demo_usernames:
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            continue  # demo user not seeded yet — don't surface it
        out.append({
            "username": user.username,
            "role": user.role,
            "role_display": user.get_role_display(),
            "full_name": user.display_name(),
            "capabilities": _ROLE_CAPABILITIES.get(user.role, "Read-only."),
        })
    return out


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True
    next_page = reverse_lazy("dashboard:home")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Only show demo cards when DEMO_MODE is enabled AND in DEBUG mode.
        # This is a UI affordance only — the cards populate the username field,
        # the user must still type the password and submit the real Django
        # auth form. Roles are NEVER derived from the card selection.
        demo_mode = bool(settings.MAJISHAMBA.get("DEMO_MODE", False)) and bool(settings.DEBUG)
        ctx["demo_mode"] = demo_mode
        ctx["demo_accounts"] = _demo_accounts() if demo_mode else []
        # Tagline for the login header
        ctx["tagline"] = "Climate-smart advisories. Extension officers decide."
        return ctx

    # Security: Django's LoginView already validates `next` against
    # REDIRECT_TO_FIELD_ALLOWED_HOSTS / same-origin by default. We don't
    # override `get_redirect_url` — Django rejects unsafe `next` URLs.


def profile(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
    return render(request, "accounts/profile.html", {"user": request.user})
