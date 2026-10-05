#!/usr/bin/env python
"""Verify the custom MCP server can be instantiated and tools are registered."""
from __future__ import annotations

import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from apps.mcp_tools.tools import TOOL_REGISTRY


def main() -> int:
    # Eight tools, two of which are action tools.
    tool_names = list(TOOL_REGISTRY.keys())
    assert len(tool_names) == 8, f"expected 8 tools, got {len(tool_names)}"
    for required in ("get_cluster_plot_history", "get_crop_calendar",
                     "get_weather_and_rainfall_context", "get_pest_alerts",
                     "get_market_price_context", "validate_advisory_evidence",
                     "create_draft_advisory_record",
                     "create_follow_up_task_after_approval"):
        assert required in tool_names, f"missing tool {required}"

    # Try to import the FastMCP-backed server module without running it.
    from apps.mcp_tools.server import main as server_main  # noqa: F401
    print(f"OK — {len(tool_names)} tools registered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
