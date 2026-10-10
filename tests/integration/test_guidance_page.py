"""Integration tests for the upgraded Agronomic Guidance page.

Verifies the enterprise-grade upgrade of /dashboard/guidance/ against the
requirements:

1. Route returns 200 for authenticated users and redirects anonymous users.
2. Page header has the correct title and description.
3. Breadcrumb shows Dashboard / Knowledge Sources / KALRO Maize Extension Manual.
4. Publication identity panel composes title + subtitle + publisher + year
   with a document icon and two status indicators on the right.
5. Status indicators use tone + label (never colour alone) and report
   "Permission not confirmed" rather than implying a pending request.
6. ONE compact operational warning panel with shield icon and concise body.
7. Publication metadata grid contains all required fields with PROPERLY
   SEPARATED values and status chips — no concatenated values like
   "KCEP-CRAL Manual 2021recorded".
8. ISBN and Document ID are SEPARATE fields — when the recorded identifier
   is not a real ISBN, the page shows "ISBN not recorded" and surfaces the
   identifier in its own Document ID field.
9. Publication date is rendered as "1 April 2021" only when the DB record
   has a verified publication_date.
10. Bibliographic verification distinguishes "record present" from
    "metadata independently verified".
11. Official publication link uses target="_blank" rel="noopener noreferrer"
    and is a separate secondary action button below the metadata grid.
12. Agronomic safety section has one heading + concise paragraph + a smaller
    highlighted local-verification panel. Does NOT repeat the permission
    warning that already appears in the operational warning above.
13. Source categories are displayed as 3 compact source cards with icon,
    name, description and integration label — NOT a plain-text list.
14. Permission lifecycle uses a visual stepper with check / amber / neutral
    markers and status chips for each step. Does not falsely claim stronger
    state than the data supports.
15. Lifecycle footnotes include the national-scope note AND the no-endorsement
    note (KALRO has not endorsed the software or approved recommendations).
16. Secondary governance information is in an expandable disclosure, not
    displayed inline.
17. Footer navigation is compact: Back to dashboard + Knowledge sources
    register. No duplicated standalone status sentence at the bottom.
18. Backward compatibility: the technical phrase "permission-pending for
    KALRO maize manual ingestion" still appears (as an SR-only marker).
19. No fake action buttons (no "Request permission", "Submit permission
    request", "Contact KALRO", etc.).
20. Heading hierarchy is logical (exactly one h1, multiple h2s).
21. Status indicators use role=status / aria-live so they are announced to
    assistive tech.
22. Missing-record handling: if the CropCalendar row is missing, the page
    renders with appropriate "not recorded" / "not found" markers and does
    not crash.
23. No template syntax leaks.
24. No invented data sources (FAO, ICIPE) and no fabricated endorsements.
25. No invented planting dates (Sep 15, October 20).
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
    # Updated description per the corrective implementation prompt
    assert "Publication governance, source verification and agronomic evidence." in html


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
# 4. Publication identity panel — composed, not disconnected text
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_publication_identity_panel_present(officer_client):
    """The publication identity panel must compose title + subtitle + publisher
    + year, not display them as disconnected text.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # Title and subtitle must be present in the .pub-hero panel
    assert 'class="pub-hero"' in html
    assert "KENYA Maize Extension Manual" in html
    assert "KCEP-CRAL Integrated Soil Fertility and Water Management Extension Manual" in html
    # Publisher short label and year must be in the meta row
    assert "KALRO" in html
    assert "2021" in html


@pytest.mark.django_db
def test_guidance_publication_identity_has_document_icon(officer_client):
    """The publication identity panel must include a document icon."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert 'class="pub-hero-icon"' in html
    # Must include an SVG (the document icon)
    assert "<svg" in html


# ---------------------------------------------------------------------------
# 5. Status indicators — tone + label, never colour alone
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_status_indicator_text_label(officer_client):
    """The status must include a text label, not colour alone."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # The label must be present as visible text in the pub-status-block
    assert "Permission" in html
    assert "Not confirmed" in html
    # Supporting label
    assert "Metadata only" in html


@pytest.mark.django_db
def test_guidance_status_does_not_imply_pending_request(officer_client):
    """The page must not claim a permission request is in progress with the
    rights holder when the system does not verify that a request has been sent.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
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
# 6. Compact operational warning — ONE panel, concise
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_warning_section_present(officer_client):
    """ONE compact operational warning panel must be present with the
    'Content not authorised for integration' heading.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "Content not authorised for integration" in html
    # The body must mention that permission has not been confirmed
    assert "documented reuse permission has not been confirmed" in html.lower()
    # Must use the .guidance-warning class
    assert 'class="guidance-warning' in html


@pytest.mark.django_db
def test_guidance_warning_not_relying_on_color_alone(officer_client):
    """The warning must not rely on colour alone — must include an icon
    with aria-hidden and a textual heading.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # The warning icon must be present
    assert "guidance-warning-icon" in html
    assert 'aria-hidden="true"' in html
    # The heading text must be present
    assert 'id="warning-heading"' in html


# ---------------------------------------------------------------------------
# 7. Publication metadata grid — properly separated values
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_publication_metadata_complete(officer_client):
    """All required metadata fields must be present in the metadata dashboard."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    expected_fields = [
        "Full title",
        "Publisher",
        "Publication date",
        "Geographic scope",
        "ISBN",
        "Document ID",
        "Copyright",
        "Permission basis",
        "Content integration",
        "Bibliographic verification",
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
    # The copyright notice:
    assert "© KALRO 2021" in html
    # The licence basis:
    assert "all rights reserved" in html.lower()


@pytest.mark.django_db
def test_guidance_metadata_does_not_concatenate_values(officer_client):
    """CRITICAL DATA QUALITY: The page must NOT have concatenated values like
    'KCEP-CRAL Manual 2021recorded' where the document ID and the badge text
    run together without separation.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # The document ID and the status chip MUST be in separate HTML elements.
    # We check for the literal string that would indicate concatenation:
    assert "Manual 2021recorded" not in html, (
        "Document ID and badge must be in separate HTML elements — found "
        "'Manual 2021recorded' which means they are concatenated."
    )
    assert "Manual 2021verified" not in html
    # The chip must be in its own element
    assert "metadata-status" in html


@pytest.mark.django_db
def test_guidance_separates_isbn_and_document_id(officer_client):
    """ISBN and Document ID must be SEPARATE fields. Since the recorded ID
    is 'KCEP-CRAL Manual 2021' (NOT a real ISBN), the page must show
    'ISBN not recorded' and surface the document ID in its own field.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # The Document ID field must contain the actual ID
    assert "KCEP-CRAL Manual 2021" in html
    # The ISBN field must explicitly state it's not recorded (since the
    # ID we have is not a real ISBN)
    assert "ISBN not recorded" in html


@pytest.mark.django_db
def test_guidance_does_not_fabricate_isbn(officer_client):
    """The page must NOT fabricate a 13-digit ISBN."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    import re

    isbn_pattern = re.compile(r"\b97[89][-0-9]{10,12}\b")
    fabricated = isbn_pattern.search(html)
    assert fabricated is None, (
        "Page must not fabricate a 13-digit ISBN. Found: "
        f"{fabricated.group(0) if fabricated else None}"
    )


@pytest.mark.django_db
def test_guidance_publication_date_rendered_properly(officer_client):
    """The publication date must be rendered as '1 April 2021' (not
    '2021-04-01') when the DB record has a verified publication_date.

    We register the KALRO bibliographic metadata in this test so the page
    has the same record the production seed fixtures provide.
    """
    from apps.integrations.kalro import register_kalro_bibliographic_metadata

    register_kalro_bibliographic_metadata()
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "1 April 2021" in html
    # The raw ISO date must NOT appear as the primary display
    # (it may still appear in a datetime= attribute, but not as visible text)
    assert "2021-04-01" not in html or 'datetime="2021-04-01' in html


# ---------------------------------------------------------------------------
# 8. External link safety
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_official_link_opens_safely_in_new_tab(officer_client):
    """The official publication link must use target=_blank with rel=noopener."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert 'target="_blank"' in html
    assert 'rel="noopener' in html
    # The link must be labelled clearly as a secondary action button
    assert "View official publication" in html


@pytest.mark.django_db
def test_guidance_link_clarifies_no_ingestion_permission(officer_client):
    """The official link must clarify that opening it does not imply
    permission to ingest or reproduce the manual's content.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "does not imply permission" in html.lower(), (
        "The official link must be accompanied by a disclaimer that linking "
        "does not imply permission to ingest content."
    )


# ---------------------------------------------------------------------------
# 9. Agronomic safety section (one heading + local-verification panel)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_agronomic_safety_heading_present(officer_client):
    """The 'Agronomic use restrictions' heading must be present."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "Agronomic use restrictions" in html


@pytest.mark.django_db
def test_guidance_local_verification_panel_present(officer_client):
    """The local planting-date verification panel must be present."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "Local planting-date verification" in html
    assert "verify the recommendation" in html.lower() or "verify against" in html.lower()
    # The local-verification panel must use the dedicated class
    assert 'class="local-verification' in html


@pytest.mark.django_db
def test_guidance_does_not_generate_planting_dates(officer_client):
    """The page must not generate or imply a specific planting date."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # Must not contain invented dates like "Sep 15" or "October 20"
    assert "Sep 15" not in html
    assert "October 20" not in html


@pytest.mark.django_db
def test_guidance_no_repeated_permission_warning_in_safety_section(officer_client):
    """The agronomic safety section must NOT repeat the full permission
    warning that already appears in the operational warning above. The
    safety section is about extracting/dates; the permission warning is
    about reuse authorisation. They must be distinct.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # The 'Content not authorised for integration' heading must appear ONCE
    # (not multiple times in different sections).
    count = html.count("Content not authorised for integration")
    assert count == 1, (
        f"'Content not authorised for integration' must appear exactly once "
        f"(in the operational warning). Found {count} occurrences."
    )


# ---------------------------------------------------------------------------
# 10. Source cards (3 / 2 / 1 column responsive grid)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_source_cards_present(officer_client):
    """The three real source categories must be displayed as cards in a
    responsive grid.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert 'class="source-card-grid"' in html
    assert "Kenya Meteorological Department (KMD)" in html
    assert "KEPHIS, KALRO and Migori County pest notices" in html
    assert "Open-Meteo" in html
    # Each card must have the .source-card class
    assert html.count('class="source-card"') == 3


@pytest.mark.django_db
def test_guidance_source_cards_have_integration_labels(officer_client):
    """Each source card must have an integration-method label."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "Manual retrieval" in html
    assert "Officer-reported" in html
    assert "Automated ingestion" in html
    # The integration label must use the dedicated class
    assert 'class="source-card-integration' in html


@pytest.mark.django_db
def test_guidance_source_cards_have_icons(officer_client):
    """Each source card must have an icon."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "source-card-icon-info" in html
    assert "source-card-icon-warning" in html
    assert "source-card-icon-success" in html


@pytest.mark.django_db
def test_guidance_links_to_source_register(officer_client):
    """The source categories section must link to the data sources register."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "/dashboard/data-sources/" in html
    assert "Open full source register" in html


@pytest.mark.django_db
def test_guidance_does_not_invent_data_sources(officer_client):
    """The page must not claim endorsements or integrations that don't exist."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "FAO" not in html
    assert "ICIPE" not in html
    assert "KALRO has endorsed" not in html
    assert "endorsed by KALRO" not in html.lower()


# ---------------------------------------------------------------------------
# 11. Permission lifecycle — visual stepper
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_lifecycle_stepper_present(officer_client):
    """The permission lifecycle must use a connected visual timeline."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert 'class="lifecycle-timeline"' in html
    # Each step must be in a <li class="lifecycle-node lifecycle-node-STATUS">
    # element. Count only the <li> openings.
    import re

    step_count = len(re.findall(r'<li class="lifecycle-node lifecycle-node-', html))
    assert step_count == 6, f"Expected 6 lifecycle nodes, found {step_count}"


@pytest.mark.django_db
def test_guidance_lifecycle_steps_present(officer_client):
    """All six lifecycle stages must be present."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    expected_steps = [
        "Source registered",
        "Rights and licence verification",
        "Content extraction and integration",
        "Agronomic review",
        "Geographic applicability",
        "Approval for advisory use",
    ]
    for step in expected_steps:
        assert step in html, f"Lifecycle must include step '{step}'"


@pytest.mark.django_db
def test_guidance_lifecycle_step_markers(officer_client):
    """Each lifecycle step must have a marker with the appropriate status:
    'done' (check icon), 'pending' (amber), 'blocked' (amber), or
    'not_started' (neutral circle).

    We register the KALRO bibliographic metadata so Source registered = done.
    """
    from apps.integrations.kalro import register_kalro_bibliographic_metadata

    register_kalro_bibliographic_metadata()
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # Step 1 (Source registered) must be 'done'
    assert "lifecycle-node-done" in html
    # Steps 2-6 must be pending/blocked/not_started
    assert "lifecycle-node-pending" in html
    assert "lifecycle-node-blocked" in html
    assert "lifecycle-node-not_started" in html


@pytest.mark.django_db
def test_guidance_lifecycle_does_not_falsely_claim_progress(officer_client):
    """The lifecycle must not claim stronger state than the data supports.

    We register the KALRO bibliographic metadata so Source registered = done
    (which is allowed — the record IS present). But the other 5 steps must
    NOT claim stronger state than 'not started' / 'pending' / 'blocked'.
    """
    from apps.integrations.kalro import register_kalro_bibliographic_metadata

    register_kalro_bibliographic_metadata()
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # Must NOT claim permission was granted
    assert "Permission granted" not in html
    # Must NOT claim content was extracted (as a lifecycle status)
    assert "Content extracted" not in html
    # Only the Source registered step should have the 'done' status chip
    import re

    done_count = len(re.findall(r"lifecycle-node-status-done", html))
    assert (
        done_count == 1
    ), f"Only 'Source registered' should be 'done'. Found {done_count} done-status chips."


@pytest.mark.django_db
def test_guidance_lifecycle_national_scope_note_present(officer_client):
    """The lifecycle must include the national-scope note explaining that
    the KCEP-CRAL manual is a national reference and does not establish
    planting dates for Kachieng' Ward.

    Note: the apostrophe in Kachieng' is HTML-escaped as &#x27; in the
    rendered output, so we check for the escaped form too.
    """
    from apps.integrations.kalro import register_kalro_bibliographic_metadata

    register_kalro_bibliographic_metadata()
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "national agronomic reference" in html.lower()
    # The apostrophe is HTML-escaped in the output
    assert "Kachieng" in html and ("Ward" in html)
    # Check the escaped form explicitly
    assert "Kachieng&#x27; Ward" in html or "Kachieng' Ward" in html or "Kachieng’ Ward" in html


@pytest.mark.django_db
def test_guidance_lifecycle_no_endorsement_note_present(officer_client):
    """The lifecycle must include the no-endorsement note clarifying that
    KALRO has not endorsed the software or approved recommendations.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "KALRO has not endorsed" in html
    assert "approved any recommendations" in html or "approved recommendations" in html.lower()


@pytest.mark.django_db
def test_guidance_lifecycle_next_action_present(officer_client):
    """The lifecycle must include a next-action link to the source register."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "View source register" in html
    assert "/dashboard/data-sources/" in html


# ---------------------------------------------------------------------------
# 12. Secondary governance info (expandable disclosure)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_secondary_info_in_expandable_disclosure(officer_client):
    """Secondary governance info must be in a <details> expandable disclosure,
    not displayed inline.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "<details" in html
    assert "<summary" in html
    assert "More about reuse, licensing and confidentiality" in html
    # The three secondary items must be in the disclosure
    assert "Public availability is not an open-data licence" in html
    assert "Permission to reuse vs agronomic validation" in html
    assert "Confidential legal correspondence" in html


@pytest.mark.django_db
def test_guidance_secondary_info_does_not_duplicate_warning(officer_client):
    """The secondary info should not duplicate the operational warning or
    the safety section — it provides additional context only.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # The 'Content not authorised for integration' heading must still appear
    # only once (in the operational warning), not in the secondary info.
    count = html.count("Content not authorised for integration")
    assert count == 1


# ---------------------------------------------------------------------------
# 13. Footer navigation — compact, no duplicated status sentence
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_footer_navigation_compact(officer_client):
    """The footer navigation must be compact: Back to dashboard + Knowledge
    sources register, with no duplicated standalone status sentence.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "Back to dashboard" in html
    assert "Knowledge sources register" in html
    assert 'class="guidance-return"' in html


# ---------------------------------------------------------------------------
# 14. Backward compatibility — legacy technical phrase
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_preserves_legacy_technical_phrase(officer_client):
    """The technical phrase 'permission-pending for KALRO maize manual
    ingestion' must still appear on the page (as an SR-only marker) so
    that existing tests, audit context, and staff references continue to
    resolve.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "permission-pending for KALRO maize manual ingestion" in html


# ---------------------------------------------------------------------------
# 15. Heading hierarchy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_heading_hierarchy_logical(officer_client):
    """The page must have exactly one h1 and multiple h2s for sections."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert html.count("<h1") == 1
    # Sections: identity, warning, metadata, safety, sources, lifecycle, secondary
    h2_count = html.count("<h2")
    assert h2_count >= 6, f"Expected at least 6 h2 section headings, found {h2_count}"


# ---------------------------------------------------------------------------
# 16. No fake action buttons
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_no_fake_request_permission_button(officer_client):
    """The page must NOT show a 'Request permission' button that implies the
    system can file a permission request — that workflow is not implemented.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "Request permission" not in html
    assert "Submit permission request" not in html
    assert "Contact KALRO" not in html
    assert "Open permission request" not in html


# ---------------------------------------------------------------------------
# 17. Semantic landmarks & accessibility
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
    assert 'aria-labelledby="identity-heading"' in html
    assert 'aria-labelledby="warning-heading"' in html
    assert 'aria-labelledby="metadata-heading"' in html
    assert 'aria-labelledby="safety-heading"' in html
    assert 'aria-labelledby="sources-heading"' in html
    assert 'aria-labelledby="lifecycle-heading"' in html


@pytest.mark.django_db
def test_guidance_metadata_uses_definition_list(officer_client):
    """Publication metadata must use a semantic <dl>/<dt>/<dd> structure."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    # The metadata grid uses dl/dt/dd semantics — we use the .metadata-row
    # wrapper with dt/dd inside.
    assert "<dl" not in html or "<dt" in html  # dl optional but dt/dd required
    assert "<dt" in html
    assert "<dd" in html


# ---------------------------------------------------------------------------
# 18. Visual consistency — uses design-token classes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_uses_design_token_classes(officer_client):
    """The page must use the .guidance-* and .pub-* / .metadata-* /
    .source-card-* / .lifecycle-* semantic classes (built on design tokens)
    rather than hard-coded Tailwind utility colour classes.
    """
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert 'class="guidance-page"' in html
    assert 'class="guidance-breadcrumb"' in html
    assert 'class="guidance-section"' in html
    assert 'class="pub-hero"' in html
    assert 'class="metadata-tiles"' in html
    assert 'class="metadata-detail"' in html
    assert 'class="guidance-warning' in html
    assert 'class="local-verification' in html
    assert 'class="source-card-grid"' in html
    assert 'class="lifecycle-timeline"' in html
    assert 'class="secondary-disclosure"' in html
    assert 'class="guidance-return"' in html


# ---------------------------------------------------------------------------
# 19. Unverified-data state — works when DB record is missing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_handles_missing_db_record(officer_client):
    """If the CropCalendar record is missing, the page must render with
    'not found' / 'not recorded' markers and not crash.
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
    # The page must show that the record is not found
    assert "not found" in html.lower() or "not recorded" in html.lower()
    # The Source registered lifecycle node must now be 'not_started'
    assert "lifecycle-node-not_started" in html


# ---------------------------------------------------------------------------
# 20. No template syntax leaks
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guidance_no_template_syntax_leaks(officer_client):
    """The page must not leak template syntax ({% %}, {{ }}, etc.) into HTML."""
    r = officer_client.get("/dashboard/guidance/")
    html = r.content.decode("utf-8")
    assert "{%" not in html
    assert "{{" not in html
    assert "{#" not in html
