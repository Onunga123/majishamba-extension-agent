"""URLs for the accounts app."""
from __future__ import annotations

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("registration/pending/", views.RegistrationPendingView.as_view(), name="registration_pending"),
    path("profile/", views.profile, name="profile"),
    path("review/", views.AccountReviewListView.as_view(), name="review"),
    path("review/<int:pk>/approve/", views.AccountApproveView.as_view(), name="approve"),
    path("review/<int:pk>/reject/", views.AccountRejectView.as_view(), name="reject"),
]
