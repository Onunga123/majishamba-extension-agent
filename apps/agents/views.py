"""Views for the agents app — show the graph and run status."""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class AgentGraphView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/agent.html"

    def get_context_data(self, **kwargs) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx["nodes"] = [
            "validate_request",
            "fetch_plot_history",
            "fetch_crop_calendar",
            "fetch_weather",
            "fetch_pest_alerts",
            "fetch_market_prices",
            "validate_evidence",
            "draft_advisory",
            "validate_output_schema",
            "save_draft",
            "officer_approval_gate",
        ]
        return ctx
