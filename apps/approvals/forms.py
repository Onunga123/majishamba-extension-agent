"""Approval form."""
from __future__ import annotations

from django import forms

from .models import OfficerApproval


class OfficerApprovalForm(forms.ModelForm):
    class Meta:
        model = OfficerApproval
        fields = ["decision", "comments"]
        widgets = {
            "decision": forms.Select(attrs={"class": "w-full border border-stone-300 rounded px-3 py-2 text-sm"}),
            "comments": forms.Textarea(attrs={"rows": 3, "class": "w-full border border-stone-300 rounded px-3 py-2 text-sm"}),
        }
        labels = {
            "decision": "Your decision",
            "comments": "Officer notes (internal)",
        }
