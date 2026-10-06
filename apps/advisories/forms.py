"""Form definitions for advisory review."""
from __future__ import annotations

from django import forms

from .models import Advisory


class AdvisoryReviewForm(forms.ModelForm):
    class Meta:
        model = Advisory
        fields = ["recommendation_type", "summary", "body", "confidence", "limitations"]
        widgets = {
            "recommendation_type": forms.Select(attrs={"class": "w-full border border-stone-300 rounded px-3 py-2 text-sm"}),
            "summary": forms.TextInput(attrs={"class": "w-full border border-stone-300 rounded px-3 py-2 text-sm"}),
            "confidence": forms.Select(attrs={"class": "w-full border border-stone-300 rounded px-3 py-2 text-sm"}),
            "limitations": forms.Textarea(attrs={"rows": 3, "class": "w-full border border-stone-300 rounded px-3 py-2 text-sm"}),
            "body": forms.Textarea(attrs={"rows": 10, "class": "w-full border border-stone-300 rounded px-3 py-2 text-sm"}),
        }
