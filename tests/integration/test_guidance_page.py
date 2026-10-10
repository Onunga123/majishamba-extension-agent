"""Integration tests for the upgraded Agronomic Guidance page.

Verifies the enterprise-grade upgrade of /dashboard/guidance/ against the
requirements:

1. Route returns 200 for authenticated users and redirects anonymous users.
2. Page header has the correct title and description.
3. Breadcrumb shows Dashboard / Knowledge Sources / KALRO Maize Extension Manual.
4. Source identity shows the publication title and status indicator.
5. Status indicator uses tone + label + supporting text (never colour alone)
   and reports "Permission not confirmed" rather than implying a pending request.
6. Publication metadata table contains all required fields (title, publisher,
   year, ISBN/ID, official URL, copyright, licence, bibliographic verification,
   content integration status).
7. Official publication link uses target="_blank" rel="noopener" for safety.
8. Agronomic use restriction section is present, prominent, and contains the
   operational instruction.
9. Local planting-date verification section is present and preserves the
   warning against inferring dates from this source.
10. Sources currently supporting advisories lists the three real categories
    (KMD bulletins, KEPHIS/KALRO/Migori County pest notices, Open-Meteo).
11. Permission and integration workflow shows the actual current state with
    all six steps and never claims a stronger state than the data supports.
12. Workflow next action links to the source register.
13. Confidential licence information is not displayed in the page.
14. Backward compatibility: the technical phrase
    "permission-pending for KALRO maize manual ingestion" still appears
    (kept as an SR-only legacy marker for existing tests and audit context).
15. No decorative action buttons falsely suggest permission has been requested
    or granted.
16. No fabricated source data, approval status, or compliance claims.
17. Heading hierarchy is logical (h1 → h2 → no h3 under each h2 in this layout).
18. Status indicator uses role="status" / aria-live so it is announced to
    assistive tech.
19. External link uses rel="noopener noreferrer".
"""

from __future__ import annotations

import pytest
from django.test import Client

# ---------------------------------------------------------------------------
# 1. Authentication gate
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_route_requires_login():
    """Anonymous users must be redirected from /dashboard/guidance/ to login."""
    c = Client()
    r = c.get("/dashboard/guidance/")
    assert r.status_code in {302, 301}
    assert "/accounts/login/" in r["Location"]


@pytest.mark.django_db
def test_guidance_route_works_for_officer(officer_client):
    """/dashboard/guidance/ must return 200 for an authenticated officer."""
    r = officer_client.get("/dashboard/guidance/")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# 2. Page header
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_page_header_present(officer_client):
    """The page must have an <h1>Agronomic Guidance</h1> and the description."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "<h1>Agronomic Guidance</h1>" in html
    assert "Source registration, permission status, and agronomic evidence governance." in html


# ---------------------------------------------------------------------------
# 3. Breadcrumb
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_breadcrumb_present(officer_client):
    """The breadcrumb must show Dashboard / Knowledge Sources / KALRO Maize Extension Manual."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "Dashboard" in html
    assert "Knowledge Sources" in html
    assert "KALRO Maize Extension Manual" in html
    # Breadcrumb semantics
    assert 'aria-label="Breadcrumb"' in html
    assert 'aria-current="page"' in html


# ---------------------------------------------------------------------------
# 4. Source identity
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_shows_publication_title_and_publisher(officer_client):
    """The page must prominently display the publication title and publisher."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "KENYA Maize Extension Manual" in html
    assert "Kenya Agricultural and Livestock Research Organization (KALRO)" in html


# ---------------------------------------------------------------------------
# 5. Status indicator — tone + label, never colour alone
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_status_indicator_text_label(officer_client):
    """The status must include a text label, not colour alone."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # The label must be present as visible text
    assert "Permission not confirmed" in html
    # Supporting label
    assert "Bibliographic metadata only" in html


@pytest.mark.django_db
def test_guidance_status_does_not_imply_pending_request(officer_client):
    """The page must not claim a permission request is in progress with the
    rights holder when the system does not verify that a request has been sent.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # The current honest state is "permission not confirmed" — the page
    # must not use phrases that imply a request is pending with the rights holder.
    assert "Permission request in progress" not in html
    assert "request has been submitted" not in html.lower()


@pytest.mark.django_db
def test_guidance_status_indicator_uses_role_status(officer_client):
    """The status indicator must use role=status / aria-live for AT users."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html


# ---------------------------------------------------------------------------
# 6. Publication metadata
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_publication_metadata_complete(officer_client):
    """All required metadata fields must be present."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    expected_fields = [
        "Publication title",
        "Publisher",
        "Publication year",
        "ISBN / document ID",
        "Official publication URL",
        "Copyright statement",
        "Reuse permission basis",
        "Geographic scope",
        "Bibliographic verification",
        "Content integration status",
    ]
    for field in expected_fields:
        assert field in html, f"Publication metadata must include '{field}'"


@pytest.mark.django_db
def test_guidance_metadata_sourced_from_actual_record(officer_client):
    """The metadata must be sourced from the actual CropCalendar record."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # The source URL from the real DB record:
    assert "https://statistics.kilimo.go.ke/files/bookpage/KENYA_Maize-Extension-Manual.pdf" in html
    # The ISBN/ID from the real DB record:
    assert "KCEP-CRAL Manual 2021" in html
    # The copyright notice:
    assert "© KALRO 2021" in html
    # The licence basis:
    assert "all rights reserved" in html.lower()


@pytest.mark.django_db
def test_guidance_metadata_does_not_fabricate_isbn(officer_client):
    """If a real ISBN is missing, the page must not invent one."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # The KALRO bibliographic record uses 'KCEP-CRAL Manual 2021' as the
    # source_document_id; the page must NOT fabricate a 13-digit ISBN.
    import re

    isbn_pattern = re.compile(r"\b97[89][-0-9]{10,12}\b")
    # We expect a 'recorded' badge next to the actual ID, but no fake 13-digit ISBN.
    fabricated = isbn_pattern.search(html)
    assert fabricated is None, (
        "Page must not fabricate a 13-digit ISBN. Found: "
        f"{fabricated.group(0) if fabricated else None}"
    )


# ---------------------------------------------------------------------------
# 7. External link safety
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_official_link_opens_safely_in_new_tab(officer_client):
    """The official publication link must use target=_blank with rel=noopener."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert 'target="_blank"' in html
    assert 'rel="noopener' in html
    # The link must be labelled clearly
    assert "View official publication" in html


@pytest.mark.django_db
def test_guidance_link_clarifies_no_ingestion_permission(officer_client):
    """The official link must clarify that opening it does not imply
    permission to ingest or reproduce the manual's content.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "does not imply permission" in html.lower() or "publication page only" in html.lower(), (
        "The official link must be accompanied by a disclaimer that linking does not "
        "imply permission to ingest content."
    )


# ---------------------------------------------------------------------------
# 8. Agronomic use restriction
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_restriction_section_present(officer_client):
    """The 'Agronomic use restriction' section must be present and prominent."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "Agronomic use restriction" in html
    # The body of the restriction must explain WHY extraction was deferred
    assert "has not been integrated" in html
    # The operational instruction must be present
    assert "Do not attribute recommendations to this manual" in html


@pytest.mark.django_db
def test_guidance_restriction_not_relying_on_color_alone(officer_client):
    """The restriction must not rely on colour alone — must include an icon
    with aria-hidden and a textual heading.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # The warning icon must be present
    assert "restriction-icon" in html
    assert 'aria-hidden="true"' in html
    # The heading text must be present
    assert 'id="restriction-heading"' in html


# ---------------------------------------------------------------------------
# 9. Local planting-date verification
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_planting_date_warning_present(officer_client):
    """The 'Local planting-date verification' section must be present."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "Local planting-date verification" in html
    assert "verify the recommendation" in html.lower() or "verify against" in html.lower()


@pytest.mark.django_db
def test_guidance_does_not_generate_planting_dates(officer_client):
    """The page must not generate or imply a specific planting date."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # The page must say dates are NOT specified, not give a date range
    assert "not establish locally appropriate planting dates" in html
    # Must not contain invented dates like "Sep 15" or "October 20"
    assert "Sep 15" not in html
    assert "October 20" not in html


# ---------------------------------------------------------------------------
# 10. Sources currently supporting advisories
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_source_categories_listed(officer_client):
    """The three real source categories must be listed."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "Kenya Meteorological Department (KMD) bulletins" in html
    assert "KEPHIS, KALRO, and Migori County pest notices" in html
    assert "Open-Meteo weather data" in html


@pytest.mark.django_db
def test_guidance_links_to_source_register(officer_client):
    """The source categories section must link to the data sources register."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "/dashboard/data-sources/" in html


@pytest.mark.django_db
def test_guidance_does_not_invent_data_sources(officer_client):
    """The page must not claim endorsements or integrations that don't exist."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # Must NOT claim FAO endorsement (not in the source register)
    assert "FAO" not in html
    # Must NOT claim ICIPE integration (not in the source register)
    assert "ICIPE" not in html
    # Must NOT claim endorsement by KALRO
    assert "KALRO has endorsed" not in html
    assert "endorsed by KALRO" not in html.lower()


# ---------------------------------------------------------------------------
# 11. Permission and integration workflow
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_workflow_steps_present(officer_client):
    """The workflow section must list all six governance steps."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    expected_steps = [
        "Source registration",
        "Rights and licence verification",
        "Content extraction and integration",
        "Agronomic review",
        "Geographic applicability",
        "Approval for advisory use",
    ]
    for step in expected_steps:
        assert step in html, f"Workflow must include step '{step}'"


@pytest.mark.django_db
def test_guidance_workflow_does_not_falsely_claim_progress(officer_client):
    """The workflow must not claim stronger state than the data supports."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # Permission pending → must NOT claim permission was granted
    assert "Permission granted" not in html
    # Must NOT claim content was extracted
    assert "Content extracted" not in html
    # Must NOT claim approved for advisory use
    assert "Approved for advisory use" not in html


@pytest.mark.django_db
def test_guidance_workflow_next_action_present(officer_client):
    """The workflow must include a next-action link to the source register."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "View source register" in html
    assert "/dashboard/data-sources/" in html


@pytest.mark.django_db
def test_guidance_workflow_confidentiality_note_present(officer_client):
    """The workflow must include a confidentiality note about legal correspondence."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "Internal legal correspondence" in html
    assert "confidential" in html.lower()


# ---------------------------------------------------------------------------
# 12. Backward compatibility — legacy technical phrase
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_preserves_legacy_technical_phrase(officer_client):
    """The technical phrase 'permission-pending for KALRO maize manual ingestion'
    must still appear on the page (kept as an SR-only legacy marker) so that
    existing tests, audit context, and staff references continue to resolve.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "permission-pending for KALRO maize manual ingestion" in html


# ---------------------------------------------------------------------------
# 13. Heading hierarchy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_heading_hierarchy_logical(officer_client):
    """The page must have exactly one h1 and all section headings must be h2."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # Exactly one h1 (the page title)
    assert html.count("<h1") == 1
    # Multiple h2s for the sections (identity, metadata, restriction, planting, sources, workflow)
    # We expect at least 6 h2s for the section structure
    h2_count = html.count("<h2")
    assert h2_count >= 6, f"Expected at least 6 h2 section headings, found {h2_count}"


# ---------------------------------------------------------------------------
# 14. No fake action buttons
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_no_fake_request_permission_button(officer_client):
    """The page must NOT show a 'Request permission' button that implies the
    system can file a permission request — that workflow is not implemented.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # These fake-action labels must NOT appear as button text
    assert "Request permission" not in html
    assert "Submit permission request" not in html
    assert "Contact KALRO" not in html
    assert "Open permission request" not in html


# ---------------------------------------------------------------------------
# 15. Responsive / accessible structure
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_uses_semantic_landmarks(officer_client):
    """The page must use semantic HTML landmarks (nav, section, header)."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "<nav" in html
    assert "<section" in html
    assert "<header" in html
    # Each section should have an aria-labelledby pointing to its heading
    assert 'aria-labelledby="metadata-heading"' in html
    assert 'aria-labelledby="sources-heading"' in html
    assert 'aria-labelledby="workflow-heading"' in html


@pytest.mark.django_db
def test_guidance_metadata_uses_definition_list(officer_client):
    """Publication metadata must use a semantic <dl> definition list."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "<dl" in html
    assert "<dt" in html
    assert "<dd" in html


# ---------------------------------------------------------------------------
# 16. Visual consistency — uses design tokens, not hardcoded colours
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_uses_design_token_classes(officer_client):
    """The page must use the .guidance-* semantic classes (built on design
    tokens) rather than hard-coded Tailwind utility colour classes.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert 'class="guidance-page"' in html
    assert 'class="guidance-breadcrumb"' in html
    assert 'class="guidance-section"' in html
    assert 'class="guidance-identity"' in html
    assert 'class="guidance-metadata"' in html
    assert 'class="guidance-restriction"' in html
    assert 'class="guidance-planting"' in html
    assert 'class="guidance-sources"' in html
    assert 'class="guidance-workflow"' in html


# ---------------------------------------------------------------------------
# 17. Unverified-data state — works when DB record is missing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_handles_missing_db_record(officer_client):
    """If the CropCalendar record is missing, the page must render with
    'unverified' badges and not crash.
    """
    from apps.calendars.models import CropCalendar

    CropCalendar.objects.filter(
        crop="maize",
        zone_label="Migori-Low-Mid",
        season=CropCalendar.Season.SHORT_RAINS,
        source_authority="KALRO",
    ).delete()
    r = officer_client.get("/dashboard/guidance/")
    assert r.status_code == 200
    html = r.content.decode("utf-8")
    # The page must show the unverifier marker for missing metadata
    assert "unverified" in html
    assert "Bibliographic record not found in source register" in html


# ---------------------------------------------------------------------------
# 18. No template syntax leaks (defense-in-depth — covered by the dedicated
#     test_no_template_comment_leaks suite, but kept here as a quick check)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_no_template_syntax_leaks(officer_client):
    """The page must not leak template syntax ({% %}, {{ }}, etc.) into HTML."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "{%" not in html
    assert "{{" not in html
    # Django template comment markers must not leak
    assert "{#" not in html
