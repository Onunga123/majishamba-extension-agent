"""Custom HTTP error handlers."""
from __future__ import annotations

from django.shortcuts import render


def permission_denied(request, exception=None):  # noqa: ARG001
    return render(request, "403.html", status=403)
