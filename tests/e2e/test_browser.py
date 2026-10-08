"""E2E browser test scaffold — uses Playwright when installed.

Skipped automatically if Playwright is not available or browsers are not installed.

This test no longer uses a hardcoded demo account. Set E2E_OFFICER_USERNAME
and E2E_OFFICER_PASSWORD in your environment to a real account you've created
via `python manage.py create_officer` + `changepassword`. Default is a
placeholder that fails the test with a clear instruction if the env vars
are not set.
"""
from __future__ import annotations

import os

import pytest

playwright = pytest.importorskip("playwright.sync_api")


@pytest.mark.e2e
@pytest.mark.django_db
@pytest.mark.skipif(
    not os.environ.get("RUN_PLAYWRIGHT_TESTS"),
    reason="Set RUN_PLAYWRIGHT_TESTS=1 to run browser tests; requires `playwright install chromium`.",
)
def test_dashboard_loads_in_browser(live_server):
    username = os.environ.get("E2E_OFFICER_USERNAME")
    password = os.environ.get("E2E_OFFICER_PASSWORD")
    if not username or not password:
        pytest.skip(
            "Set E2E_OFFICER_USERNAME and E2E_OFFICER_PASSWORD to a real account "
            "(created via `python manage.py create_officer` + `changepassword`) to run this test."
        )

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(live_server.url + "/accounts/login/")
        page.fill('input[name="username"]', username)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')
        page.wait_for_url("**/dashboard/")
        assert "Kachieng" in page.title() or "MajiShamba" in page.title()
        browser.close()
