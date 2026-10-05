"""Form definitions for advisory review."""
from __future__ import annotations

from django import forms

from .models import Advisory


class AdvisoryReviewForm(forms.ModelForm):
    class Meta:
        model = Advisory
        fields = ["recommendation_type", "summary", "body", "confidence", "limitations"]
        widgets = {
            "limitations": forms.Textarea(attrs={"rows": 3}),
            "body": forms.Textarea(attrs={"rows": 10}),
        }
