"""Views for the accounts app."""
from __future__ import annotations

from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True
    next_page = reverse_lazy("dashboard:home")


def profile(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
    return render(request, "accounts/profile.html", {"user": request.user})
