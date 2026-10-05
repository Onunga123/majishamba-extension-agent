"""E2E browser test scaffold — uses Playwright when installed.

Skipped automatically if Playwright is not available or browsers are not installed.
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
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(live_server.url + "/accounts/login/")
        page.fill('input[name="username"]', "nyatike_officer")
        page.fill('input[name="password"]', "majishamba-demo-2025")
        page.click('button[type="submit"]')
        page.wait_for_url("**/dashboard/")
        assert "Kachieng" in page.title() or "MajiShamba" in page.title()
        browser.close()
