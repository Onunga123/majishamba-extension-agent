"""Pytest configuration for MajiShamba Extension Agent."""
from __future__ import annotations

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

import pytest
from django.contrib.auth import get_user_model
from django.test import Client


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
