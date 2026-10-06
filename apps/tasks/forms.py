from __future__ import annotations

from django import forms

from .models import FieldFinding, FollowUpTask


class FieldFindingForm(forms.ModelForm):
    class Meta:
        model = FieldFinding
        fields = [
            "visit_date",
            "observations",
            "missing_information",
            "follow_up_notes",
        ]
        widgets = {
            "observations": forms.Textarea(attrs={"rows": 4}),
            "missing_information": forms.Textarea(attrs={"rows": 2}),
            "follow_up_notes": forms.Textarea(attrs={"rows": 2}),
        }


class TaskStatusForm(forms.Form):
    status = forms.ChoiceField(choices=FollowUpTask.Status.choices)
