"""Views for the agents app — show the graph and run status."""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView


class AgentGraphView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Show the LangGraph workflow diagram and tool catalogue reference.

    Phase D authorization: gated on the application role, not Django's
    ``is_staff`` flag. Extension Officers, Supervisors, and System
    Administrators may view the agent graph reference. Viewers are
    denied (403) — a Viewer with ``is_staff=True`` (e.g. mis-provisioned
    via ``create_officer --role viewer``) must NOT gain access. This
    preserves the existing ``test_viewer_cannot_open_agent_graph``
    assertion in tests/security/test_security.py.
    """

    template_name = "dashboard/agent.html"
    raise_exception = True

    def test_func(self) -> bool:  # type: ignore[override]
        user = self.request.user
        return bool(
            user.is_authenticated
            and (user.is_officer() or user.is_system_admin())
        )

    def get_context_data(self, **kwargs) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx["nodes"] = [
            "validate_request",
            "fetch_plot_history",
            "fetch_crop_calendar",
            "load_calendar_from_borrowed_mcp",
            "fetch_weather",
            "fetch_pest_alerts",
            "fetch_market_prices",
            "validate_evidence",
            "draft_advisory",
            "validate_output_schema",
            "use_fallback_template",
            "save_draft",
            "officer_approval_gate",
        ]
        return ctx
