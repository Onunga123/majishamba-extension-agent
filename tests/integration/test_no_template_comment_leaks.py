"""Regression test: raw template-comment syntax ({# ... #}) must NEVER
reach the browser as visible text.

This test was added after a production bug where multi-line {# ===== ...
===== #} comments in templates/dashboard/home.html were rendered as
literal text in the user's browser because Django's {# ... #} syntax
only supports single-line comments — the lexer regex does not have
DOTALL, so multi-line blocks pass through unchanged.

Root cause: Django's `django.template.base.Lexer.create_token` uses
`comment_tag_re = re.compile(r"\\{#.*?#\\}")` without `re.S`, so multi-line
`{# ... #}` blocks are not recognized as comments.

Fix: developers must use single-line `{# ... #}` comments OR the
`{% comment %}...{% endcomment %}` block tag for multi-line comments.
Decorative section-divider comments should not be used at all — use
semantic <section> + aria-labelledby instead.

These tests guard against the same bug recurring on any major page.
"""
from __future__ import annotations

import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client


User = get_user_model()


# ---------------------------------------------------------------------------
# Helper: assert no template-comment syntax leaks
# ---------------------------------------------------------------------------

LEAK_PATTERNS = [
    re.compile(r"\{#.*?#\}", re.S),         # {# ... #} (single OR multi-line)
    re.compile(r"\{%.*?%\}", re.S),         # {% ... %} tags (only leaks if malformed)
    re.compile(r"\{\{\s*\w", re.S),         # {{ var }} (only leaks if malformed)
]


def _assert_no_template_syntax_leaks(html: str, page_label: str) -> None:
    """Assert that the rendered HTML contains no raw Django template syntax."""
    for pat in LEAK_PATTERNS:
        matches = pat.findall(html)
        # Filter out false positives: `{{` could legitimately appear in JS text.
        # We only care about actual Django template leaks: {# ... #} (always a
        # comment, never visible) and {% ... %} (always a tag, never visible).
        real_leaks = []
        for m in matches:
            if m.startswith("{#") or m.startswith("{%"):
                real_leaks.append(m)
        assert not real_leaks, (
            f"RAW TEMPLATE SYNTAX LEAK on {page_label}: {real_leaks[:3]} — "
            "the user will see this text in their browser. "
            "Use single-line {# ... #} comments or "
            "{% comment %}...{% endcomment %} for multi-line."
        )


# ---------------------------------------------------------------------------
# Anonymous pages: login, register, registration_pending
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_no_template_syntax_leaks_on_login_page():
    c = Client()
    r = c.get("/accounts/login/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/accounts/login/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_register_page():
    c = Client()
    r = c.get("/accounts/register/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/accounts/register/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_registration_pending_page():
    c = Client()
    r = c.get("/accounts/registration/pending/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/accounts/registration/pending/")


# ---------------------------------------------------------------------------
# Authenticated pages: dashboard, advisories, tasks, audit, etc.
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_no_template_syntax_leaks_on_dashboard(officer_client):
    """The dashboard is where the original {# ===== ... ===== #} leak was found.
    This test guards against regression."""
    r = officer_client.get("/dashboard/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/dashboard/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_dashboard_with_search(officer_client):
    """Search and filter parameters must not introduce leaks."""
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/dashboard/", {"q": "Sori", "status": "draft"})
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/dashboard/?q=Sori&status=draft")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_dashboard_with_empty_state(officer_client):
    """The empty state (no clusters, no advisories) must not introduce leaks."""
    r = officer_client.get("/dashboard/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/dashboard/ (empty state)")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_dashboard_map(officer_client):
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/dashboard/map/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/dashboard/map/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_dashboard_about(officer_client):
    r = officer_client.get("/dashboard/about/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/dashboard/about/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_dashboard_guidance(officer_client):
    r = officer_client.get("/dashboard/guidance/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/dashboard/guidance/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_dashboard_data_sources(officer_client):
    r = officer_client.get("/dashboard/data-sources/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/dashboard/data-sources/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_advisories_list(officer_client):
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    r = officer_client.get("/advisories/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/advisories/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_advisory_detail(officer_client):
    from django.core.management import call_command
    from io import StringIO
    from tests.factories.models import AdvisoryFactory
    call_command("seed_kachieng_clusters", stdout=StringIO())
    a = AdvisoryFactory(status="draft")
    r = officer_client.get(f"/advisories/{a.id}/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), f"/advisories/{a.id}/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_advisory_request_page(officer_client):
    r = officer_client.get("/advisories/request/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/advisories/request/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_approval_gate(supervisor_client):
    from django.core.management import call_command
    from io import StringIO
    from tests.factories.models import AdvisoryFactory
    call_command("seed_kachieng_clusters", stdout=StringIO())
    a = AdvisoryFactory(status="draft")
    r = supervisor_client.get(f"/approvals/{a.id}/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), f"/approvals/{a.id}/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_tasks_list(officer_client):
    r = officer_client.get("/tasks/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/tasks/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_task_detail(officer_client):
    from tests.factories.models import AdvisoryFactory
    from apps.tasks.models import FollowUpTask
    a = AdvisoryFactory(status="approved")
    t = FollowUpTask.objects.create(
        approved_advisory=a, task_type=FollowUpTask.TaskType.FIELD_VISIT,
        deadline="2030-01-01", status=FollowUpTask.Status.ASSIGNED,
    )
    r = officer_client.get(f"/tasks/{t.id}/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), f"/tasks/{t.id}/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_audit_list(officer_client):
    r = officer_client.get("/audit/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/audit/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_clusters_detail(officer_client):
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    from apps.clusters.models import FarmerCluster
    cluster = FarmerCluster.objects.first()
    r = officer_client.get(f"/clusters/{cluster.cluster_id}/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), f"/clusters/{cluster.cluster_id}/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_integrations_index(officer_client):
    r = officer_client.get("/integrations/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/integrations/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_profile_page(officer_client):
    r = officer_client.get("/accounts/profile/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/accounts/profile/")


@pytest.mark.django_db
def test_no_template_syntax_leaks_on_account_review_page(supervisor_client):
    r = supervisor_client.get("/accounts/review/")
    assert r.status_code == 200
    _assert_no_template_syntax_leaks(r.content.decode("utf-8"), "/accounts/review/")


# ---------------------------------------------------------------------------
# Static-source audit: scan every template file in the repo for multi-line
# {# ... #} comments (the pattern that triggers the bug)
# ---------------------------------------------------------------------------

def test_no_multiline_template_comments_in_repo():
    """Scan every .html template file in the repo and assert that NO multi-line
    {# ... #} comments exist. Django's {# ... #} syntax is single-line only;
    multi-line blocks leak through to the rendered HTML.

    This test catches the bug at the source: if any developer adds a
    multi-line {# ... #} comment in the future, this test will fail
    immediately.
    """
    import os
    template_dirs = ["templates", "apps"]
    problem_files = []
    for root in template_dirs:
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            for f in files:
                if not f.endswith(".html"):
                    continue
                path = os.path.join(dirpath, f)
                with open(path, encoding="utf-8") as fp:
                    content = fp.read()
                # Find all {# ... #} blocks (single + multi-line)
                matches = re.findall(r"\{#.*?#\}", content, re.S)
                multi_line = [m for m in matches if "\n" in m]
                if multi_line:
                    problem_files.append((path, len(multi_line)))
    assert not problem_files, (
        "Found multi-line {# ... #} comments in "
        f"{len(problem_files)} template file(s) — these will leak to the browser as raw text:\n"
        + "\n".join(f"  {count} in {path}" for path, count in problem_files)
        + "\n\nFix: replace with single-line {# ... #} OR {% comment %}...{% endcomment %}"
    )


def test_no_decorative_separator_comments_in_repo():
    """Scan every .html template for decorative {# ===== ... ===== #} comments
    that span multiple lines. These are both a leak risk AND a code smell —
    sections should be visually separated using semantic HTML (e.g.
    <section aria-labelledby="...">) and the design system, not developer
    comments."""
    import os
    template_dirs = ["templates", "apps"]
    problems = []
    for root in template_dirs:
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            for f in files:
                if not f.endswith(".html"):
                    continue
                path = os.path.join(dirpath, f)
                with open(path, encoding="utf-8") as fp:
                    content = fp.read()
                # Find {# followed by ===== pattern (decorative)
                matches = re.findall(r"\{#\s*={3,}.*?={3,}\s*#\}", content, re.S)
                if matches:
                    problems.append((path, len(matches)))
    assert not problems, (
        "Found decorative {# ===== ... ===== #} separator comments in "
        f"{len(problems)} template file(s) — these leak through Django's template "
        "engine as raw text. Use semantic <section> + aria-labelledby instead.\n"
        + "\n".join(f"  {count} in {path}" for path, count in problems)
    )


# ---------------------------------------------------------------------------
# Specific regression test for the original bug
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dashboard_does_not_contain_section_divider_text():
    """The original bug report showed 'HEADER STRIP — location, last updated,
    refresh' visible in the dashboard HTML. That text came from a multi-line
    {# ===== ... ===== #} comment that leaked. This test asserts the specific
    leaked text is gone."""
    from django.core.management import call_command
    from io import StringIO
    call_command("seed_kachieng_clusters", stdout=StringIO())
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u, _ = User.objects.get_or_create(
        username="regression_officer",
        defaults={"role": "extension_officer", "full_name": "Regression",
                  "sub_county": "Nyatike", "ward": "Kachieng", "is_staff": True},
    )
    u.set_password("test-password-1")
    u.save()
    c = Client()
    c.force_login(u)
    r = c.get("/dashboard/")
    html = r.content.decode("utf-8")
    # The leaked comment text must NOT appear
    assert "HEADER STRIP" not in html
    assert "NEEDS YOUR ATTENTION — actionable cards" not in html
    assert "PRIMARY CTA — request advisory" not in html
    assert "CLUSTERS — responsive table" not in html
    assert "RECENT ADVISORIES — grouped by status" not in html
    assert "WEATHER / PESTS / GUIDANCE" not in html
    assert "AUDIT TIMELINE — readable" not in html
    # The decorative === separator pattern must NOT appear
    assert "=========" not in html
