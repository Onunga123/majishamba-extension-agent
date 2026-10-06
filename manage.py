#!/usr/bin/env python
"""Django management entry point for MajiShamba Extension Agent."""
from __future__ import annotations

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - exercised only when deps missing
        raise ImportError(
            "Couldn't import Django. Activate your virtualenv and install deps "
            "with `uv sync` or `pip install -e .[dev]`."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
