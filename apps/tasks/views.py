from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from .models import FollowUpTask


class FollowUpTaskListView(LoginRequiredMixin, ListView):
    model = FollowUpTask
    template_name = "tasks/list.html"
    context_object_name = "tasks"
    paginate_by = 25
