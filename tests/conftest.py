"""Pytest configuration for MajiShamba Extension Agent."""
from __future__ import annotations

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
# Skip Ollama by default in tests so the suite is fast (<5s) and deterministic.
# Set MAJISHAMBA_SKIP_OLLAMA=0 to disable this and exercise the live model path.
os.environ.setdefault("MAJISHAMBA_SKIP_OLLAMA", "1")
django.setup()

import pytest
from django.contrib.auth import get_user_model
from django.test import Client


@pytest.fixture(autouse=True)
def _skip_ollama_in_tests(monkeypatch):
    """Force-skip Ollama in tests unless the caller explicitly disables it."""
    if os.environ.get("MAJISHAMBA_SKIP_OLLAMA", "1") == "1":
        monkeypatch.setenv("MAJISHAMBA_SKIP_OLLAMA", "1")
    # Also reset the module-level SKIP_OLLAMA flag in apps.agents.graph so the
    # autouse fixture takes effect even if the module was imported earlier.
    from apps.agents import graph as _graph
    monkeypatch.setattr(_graph, "SKIP_OLLAMA", True)


@pytest.fixture
def officer(db):
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="test_officer",
        defaults={"role": User.Role.EXTENSION_OFFICER, "full_name": "Test Officer", "sub_county": "Nyatike", "ward": "Kachieng"},
    )
    user.set_password("test-password")
    user.is_staff = True
    user.save()
    return user


@pytest.fixture
def supervisor(db):
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="test_supervisor",
        defaults={"role": User.Role.SUPERVISOR, "full_name": "Test Supervisor", "sub_county": "Nyatike", "ward": "Kachieng"},
    )
    user.set_password("test-password")
    user.is_staff = True
    user.save()
    return user


@pytest.fixture
def viewer(db):
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="test_viewer",
        defaults={"role": User.Role.VIEWER, "full_name": "Test Viewer", "sub_county": "Nyatike", "ward": "Kachieng"},
    )
    user.set_password("test-password")
    user.save()
    return user


@pytest.fixture
def officer_client(officer):
    c = Client()
    c.force_login(officer)
    return c


@pytest.fixture
def supervisor_client(supervisor):
    c = Client()
    c.force_login(supervisor)
    return c


@pytest.fixture
def viewer_client(viewer):
    c = Client()
    c.force_login(viewer)
    return c


@pytest.fixture
def anonymous_client():
    return Client()
