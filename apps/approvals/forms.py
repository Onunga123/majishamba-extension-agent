"""Approval form."""
from __future__ import annotations

from django import forms

from .models import OfficerApproval


class OfficerApprovalForm(forms.ModelForm):
    class Meta:
        model = OfficerApproval
        fields = ["decision", "comments"]
        widgets = {"comments": forms.Textarea(attrs={"rows": 3})}
