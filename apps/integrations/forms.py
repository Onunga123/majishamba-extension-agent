"""Forms for officer-supplied data ingestion (KMD bulletins, pest field reports)."""

from __future__ import annotations

import datetime as dt

from django import forms

# Shared input class — matches the authenticated-app Tailwind convention used
# by the audit list, dashboard search, and advisories list inputs. Applied to
# every widget so inputs, selects, and textareas fill their container width
# and have a consistent border, focus ring, and padding. This prevents the
# mobile horizontal overflow caused by browser-default widget sizing.
INPUT_CLASS = (
    "w-full border border-stone-300 rounded px-3 py-2 text-sm "
    "focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 "
    "outline-none transition"
)


class KMDBulletinForm(forms.Form):
    """Officer transcribes metadata from a KMD bulletin they've manually read."""

    PRODUCT_CHOICES = [
        ("Daily Forecast", "Daily Forecast"),
        ("5 Days Forecast", "5 Days Forecast"),
        ("7 Days Forecast", "7 Days Forecast"),
        ("County Forecast", "County Forecast (Migori)"),
        ("Lake Victoria Fishing Forecast", "Lake Victoria Fishing Forecast (regional)"),
        ("Seasonal Outlook", "Seasonal Outlook"),
    ]

    COVERAGE_CHOICES = [
        ("county", "County (e.g. Migori)"),
        ("regional", "Regional (e.g. Lake Victoria Basin)"),
        ("national", "National"),
    ]

    product_type = forms.ChoiceField(
        choices=PRODUCT_CHOICES,
        label="KMD product",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    publication_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
        label="Issue date (publication date)",
    )
    valid_from = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
        required=False,
        label="Valid from (forecast validity start)",
    )
    valid_to = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
        required=False,
        label="Valid to (forecast validity end)",
    )
    geographic_scope = forms.CharField(
        max_length=160,
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Migori County, Lake Victoria Basin",
                "class": INPUT_CLASS,
            }
        ),
        label="Geographic scope (as published)",
    )
    coverage_level = forms.ChoiceField(
        choices=COVERAGE_CHOICES,
        initial="county",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    area_label = forms.CharField(
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Migori County",
                "class": INPUT_CLASS,
            }
        ),
        label="Area label for storage",
    )
    period = forms.ChoiceField(
        choices=[
            ("daily_forecast", "Daily forecast"),
            ("5_day_forecast", "5-day forecast"),
            ("7_day_forecast", "7-day forecast"),
            ("10_day_forecast", "10-day forecast (legacy)"),
            ("seasonal_outlook", "Seasonal outlook"),
            ("last_30_days", "Last 30 days (observation)"),
            ("last_7_days", "Last 7 days (observation)"),
        ],
        label="Period",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    forecast_summary = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": INPUT_CLASS}),
        label="Qualitative forecast (as published, e.g. 'Showers and thunderstorms over parts of Migori')",
    )
    rainfall_mm = forms.FloatField(
        required=False,
        label="Rainfall (mm) — leave blank if the bulletin does not specify a numeric value",
        widget=forms.NumberInput(attrs={"step": "any", "class": INPUT_CLASS}),
    )
    rainfall_period_note = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. 'Migori County, 24h forecast total'",
                "class": INPUT_CLASS,
            }
        ),
        label="Rainfall period/scope note (REQUIRED if you enter a rainfall value)",
    )
    onset_status = forms.ChoiceField(
        choices=[
            ("unknown", "Unknown (default)"),
            ("onset_confirmed", "Onset confirmed by KMD"),
            ("onset_delayed", "Onset delayed by KMD"),
            ("false_start", "False start reported by KMD"),
        ],
        initial="unknown",
        help_text="Set to 'unknown' unless KMD explicitly reports onset for this area.",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    source_url = forms.URLField(
        required=False,
        widget=forms.URLInput(
            attrs={
                "placeholder": "https://meteo.go.ke/our-products/...",
                "class": INPUT_CLASS,
            }
        ),
        label="Link to official KMD page",
    )


class OfficerFieldReportForm(forms.Form):
    """Officer submits a verified local pest field report."""

    SEVERITY_CHOICES = [
        ("not_specified", "Not specified (default — do not inflate)"),
        ("low", "Low"),
        ("moderate", "Moderate"),
        ("high", "High (only if you observed confirmed high pressure)"),
        ("extreme", "Extreme (only if you observed confirmed extreme pressure)"),
    ]

    COVERAGE_CHOICES = [
        ("ward", "Ward (e.g. Kachieng)"),
        ("locality", "Locality (e.g. Sori)"),
        ("county", "County (e.g. Migori)"),
        ("sub_county", "Sub-county (e.g. Nyatike)"),
    ]

    pest = forms.CharField(
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Fall Armyworm (Spodoptera frugiperda)",
                "class": INPUT_CLASS,
            }
        ),
    )
    crop = forms.CharField(
        max_length=80,
        initial="maize",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS}),
    )
    observation_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
        label="Observation date",
    )
    coverage = forms.CharField(
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Kachieng Ward, or Sori locality",
                "class": INPUT_CLASS,
            }
        ),
        label="Coverage description",
    )
    coverage_level = forms.ChoiceField(
        choices=COVERAGE_CHOICES,
        initial="ward",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    severity = forms.ChoiceField(
        choices=SEVERITY_CHOICES,
        initial="not_specified",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    advisory = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": INPUT_CLASS}),
        required=False,
        label="Observation notes (what you saw, where, when)",
    )


class PublishedPestNoticeForm(forms.Form):
    """Officer transcribes metadata from a published official pest notice (KEPHIS, county report)."""

    AUTHORITY_CHOICES = [
        ("KEPHIS", "Kenya Plant Health Inspectorate Service"),
        ("Migori County Department of Agriculture", "Migori County Department of Agriculture"),
        (
            "Ministry of Agriculture and Livestock Development",
            "Ministry of Agriculture and Livestock Development",
        ),
        ("KALRO", "KALRO (pest factsheet — background reference)"),
    ]

    authority = forms.ChoiceField(
        choices=AUTHORITY_CHOICES,
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    product_type = forms.CharField(
        max_length=80,
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Pest alert notice, County agricultural report",
                "class": INPUT_CLASS,
            }
        ),
    )
    publication_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
        label="Publication date",
    )
    pest = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS}),
    )
    crop = forms.CharField(
        max_length=80,
        initial="maize",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS}),
    )
    severity = forms.ChoiceField(
        choices=[
            ("not_specified", "Not specified (default — do not inflate)"),
            ("low", "Low"),
            ("moderate", "Moderate"),
            ("high", "High (only if the notice explicitly states high)"),
            ("extreme", "Extreme (only if the notice explicitly states extreme)"),
        ],
        initial="not_specified",
        help_text="Store EXACTLY as published. Do NOT inflate.",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    geographic_scope = forms.CharField(
        max_length=160,
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. National, Migori County, Lake Victoria Basin",
                "class": INPUT_CLASS,
            }
        ),
    )
    coverage_level = forms.ChoiceField(
        choices=[("national", "National"), ("regional", "Regional"), ("county", "County")],
        initial="county",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    source_url = forms.URLField(
        required=False,
        label="Link to the official notice",
        widget=forms.URLInput(attrs={"class": INPUT_CLASS}),
    )
    source_document_id = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. KEPHIS-FAW-2026-10",
                "class": INPUT_CLASS,
            }
        ),
        label="Document/notice ID (if assigned by the authority)",
    )
