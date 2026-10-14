"""HTTP view that lists all custom MCP tools and exposes them as JSON (admin/test helper)."""
from __future__ import annotations

import inspect

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View

from .tools import TOOL_REGISTRY


class MCPToolListView(LoginRequiredMixin, UserPassesTestMixin, View):
    """List the MCP tool catalogue.

    Phase D authorization: gated on the application role, not Django's
    ``is_staff`` flag. Extension Officers, Supervisors, and System
    Administrators may inspect the tool catalogue. Viewers are denied
    (403) — a Viewer with ``is_staff=True`` (e.g. mis-provisioned via
    ``create_officer --role viewer``) must NOT gain access.
    """

    raise_exception = True

    def test_func(self) -> bool:  # type: ignore[override]
        user = self.request.user
        return bool(
            user.is_authenticated
            and (user.is_officer() or user.is_system_admin())
        )

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
    """Execute a registered MCP tool by name.

    Phase D authorization: gated on the application role, not ``is_staff``.
    Only Extension Officers, Supervisors, and System Administrators may
    call tools. The authenticated user is bound as the actor for every
    tool call (see ``post``) — client-supplied ``actor``/``actor_id``
    values are stripped from the body and cannot override the
    authenticated identity (D-12).
    """

    raise_exception = True

    def test_func(self) -> bool:  # type: ignore[override]
        user = self.request.user
        return bool(
            user.is_authenticated
            and (user.is_officer() or user.is_system_admin())
        )

    def post(self, request: HttpRequest, tool_name: str) -> JsonResponse:
        import json
        try:
            body = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid JSON"}, status=400)
        spec = TOOL_REGISTRY.get(tool_name)
        if not spec:
            return JsonResponse({"error": f"unknown tool {tool_name}"}, status=404)
        # D-12: the authenticated request user is the authoritative actor.
        # Strip any client-supplied actor/actor_id from the body so a
        # caller cannot forge audit attribution or impersonate another
        # user. The injected values below override anything the caller
        # tried to supply.
        body.pop("actor", None)
        body.pop("actor_id", None)
        fn = spec["fn"]
        params = inspect.signature(fn).parameters
        if "actor" in params:
            body["actor"] = request.user
        if "actor_id" in params:
            body["actor_id"] = request.user.id
        try:
            result = fn(**body)
        except TypeError as exc:
            return JsonResponse({"error": f"bad arguments: {exc}"}, status=400)
        return JsonResponse({"result": result})
