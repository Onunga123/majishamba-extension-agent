"""Standalone MCP server entry point using the official MCP Python SDK.

Run with:
    python manage.py shell
    >>> from apps.mcp_tools.server import main
    >>> main()  # stdio transport

Or with the project script:
    majishamba-mcp

This exposes the tools defined in apps.mcp_tools.tools to any MCP-aware
client (e.g. Claude Desktop, an agent, a test harness) over stdio.

The server is intentionally thin: every tool call is delegated to the same
function the LangGraph agent uses, so behaviour is identical whether the
tool is called in-process by the agent, from the Django UI, or from an
external MCP client.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

logger = logging.getLogger("majishamba.mcp_server")


def _setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    import django  # type: ignore[import-not-found]

    django.setup()


def main() -> None:
    """Run the MCP server over stdio using the official MCP Python SDK."""
    _setup_django()
    from apps.mcp_tools.tools import TOOL_REGISTRY

    # Import the MCP SDK lazily so the file imports cleanly without the SDK installed.
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover
        logger.error("MCP SDK not available: %s. Falling back to JSON-RPC-over-stdio shim.", exc)
        _json_rpc_stdio_shim()
        return

    mcp = FastMCP("majishamba-extension-mcp")

    for name, spec in TOOL_REGISTRY.items():
        fn = spec["fn"]
        description = spec["description"]

        # FastMCP registers tools by passing a callable. We wrap each tool
        # with a thin closure that defers to the underlying function and
        # passes kwargs through.
        def make_wrapper(_name: str, _fn: Any) -> Any:
            def wrapper(**kwargs: Any) -> dict[str, Any]:
                return _fn(**kwargs)

            wrapper.__name__ = _name
            wrapper.__doc__ = description
            return wrapper

        mcp.tool(name=name, description=description)(make_wrapper(name, fn))

    mcp.run(transport="stdio")


def _json_rpc_stdio_shim() -> None:
    """Tiny stdio JSON-RPC fallback when the MCP SDK is not installed.

    Supports a minimal subset:
      - tools/list
      - tools/call
    """
    from apps.mcp_tools.tools import TOOL_REGISTRY

    writer = sys.stdout
    for raw in sys.stdin:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        req_id = msg.get("id")
        if method == "initialize":
            writer.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"serverInfo": {"name": "majishamba-extension-mcp", "version": "0.1.0"}}}) + "\n")
            writer.flush()
        elif method == "tools/list":
            tools = [{"name": n, "description": s["description"]} for n, s in TOOL_REGISTRY.items()]
            writer.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}) + "\n")
            writer.flush()
        elif method == "tools/call":
            params = msg.get("params", {})
            tool_name = params.get("name")
            args = params.get("arguments", {}) or {}
            spec = TOOL_REGISTRY.get(tool_name)
            if not spec:
                writer.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"unknown tool {tool_name}"}}) + "\n")
                writer.flush()
                continue
            try:
                result = spec["fn"](**args)
            except Exception as exc:  # pragma: no cover
                writer.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(exc)}}) + "\n")
                writer.flush()
                continue
            writer.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}}) + "\n")
            writer.flush()
        else:
            writer.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"unknown method {method}"}}) + "\n")
            writer.flush()


if __name__ == "__main__":  # pragma: no cover
    main()
