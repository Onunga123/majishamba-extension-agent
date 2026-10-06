"""HTTP view that lists all custom MCP tools and exposes them as JSON (admin/test helper)."""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View

from .tools import TOOL_REGISTRY


class MCPToolListView(LoginRequiredMixin, UserPassesTestMixin, View):
    raise_exception = True

    def test_func(self) -> bool:  # type: ignore[override]
        return self.request.user.is_authenticated and self.request.user.is_staff

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        return JsonResponse({
            "server": "majishamba-extension-mcp",
            "version": "0.1.0",
            "tools": [
                {"name": name, "description": spec["description"],
                 "required": spec["required"], "optional": spec["optional"]}
                for name, spec in TOOL_REGISTRY.items()
            ],
            "borrowed_mcp_server": "official filesystem MCP server (used in development to load approved crop-calendar PDFs from docs/calendars/)",
        })


class MCPToolCallView(LoginRequiredMixin, UserPassesTestMixin, View):
    raise_exception = True

    def test_func(self) -> bool:  # type: ignore[override]
        return self.request.user.is_authenticated and self.request.user.is_staff

    def post(self, request: HttpRequest, tool_name: str) -> JsonResponse:
        import json
        try:
            body = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid JSON"}, status=400)
        spec = TOOL_REGISTRY.get(tool_name)
        if not spec:
            return JsonResponse({"error": f"unknown tool {tool_name}"}, status=404)
        try:
            result = spec["fn"](**body)
        except TypeError as exc:
            return JsonResponse({"error": f"bad arguments: {exc}"}, status=400)
        return JsonResponse({"result": result})
