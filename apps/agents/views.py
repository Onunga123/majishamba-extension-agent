"""Views for the agents app — show the graph and run status."""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView


class AgentGraphView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "dashboard/agent.html"
    raise_exception = True

    def test_func(self) -> bool:  # type: ignore[override]
        return self.request.user.is_authenticated and self.request.user.is_staff

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
