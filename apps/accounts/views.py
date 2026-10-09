"""Views for the accounts app — registration, login, account review."""
from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django import forms
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View

from apps.audit.service import log_audit_event

from .models import User


# --- Registration form ---
class RegistrationForm(forms.ModelForm):
    """Public registration form. Requested role is stored separately from effective role.
    The user does NOT get their requested role until an administrator approves it."""

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "auth-input"}),
        help_text="At least 10 characters. Avoid common passwords.",
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "auth-input"}),
        help_text="Enter the same password as before, for verification.",
    )
    requested_role = forms.ChoiceField(
        choices=[
            ("extension_officer", "Extension Officer — Request advisories, review drafts, manage field tasks"),
            ("supervisor", "Supervisor — Review and approve advisories, verify field findings"),
            ("viewer", "Viewer — Read-only access to dashboard and advisories"),
        ],
        label="Requested role",
        help_text="Your request will be reviewed by an administrator. You will not receive this role until approved.",
        widget=forms.Select(attrs={"class": "auth-input"}),
    )
    organization = forms.CharField(
        max_length=160, required=False,
        help_text="Office or organization (e.g. sub-county agricultural office)",
        widget=forms.TextInput(attrs={"class": "auth-input"}),
    )
    email = forms.EmailField(
        required=False,
        help_text="Used for account communications if email is configured.",
        widget=forms.EmailInput(attrs={"class": "auth-input"}),
    )

    class Meta:
        model = User
        fields = ["full_name", "username", "email", "requested_role", "organization", "sub_county", "ward"]
        labels = {
            "full_name": "Full name",
            "username": "Username",
            "sub_county": "Sub-county",
            "ward": "Ward",
        }
        help_texts = {
            "username": "Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
        }
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "auth-input"}),
            "username": forms.TextInput(attrs={"class": "auth-input"}),
            "sub_county": forms.TextInput(attrs={"class": "auth-input"}),
            "ward": forms.TextInput(attrs={"class": "auth-input"}),
        }

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match.")
        if p1 and len(p1) < 10:
            raise forms.ValidationError("Password must be at least 10 characters.")
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.role = User.Role.VIEWER  # Always start as viewer
        user.approval_status = User.ApprovalStatus.PENDING
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user


class RegisterView(View):
    """Public registration page. Creates a PENDING account — no operational access."""

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard:home")
        form = RegistrationForm()
        return render(request, "accounts/register.html", {"form": form})

    def post(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard:home")
        form = RegistrationForm(request.POST)
        if not form.is_valid():
            return render(request, "accounts/register.html", {"form": form})
        user = form.save()
        log_audit_event(
            actor=None,
            action="account:register",
            target=user,
            metadata={"username": user.username, "requested_role": user.requested_role},
        )
        messages.info(request, "Your account has been created and is pending review by an administrator.")
        return redirect("accounts:registration_pending")


class RegistrationPendingView(View):
    """Shows the pending-account status page."""

    def get(self, request):
        return render(request, "accounts/registration_pending.html")


# --- Login view ---
class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True
    next_page = reverse_lazy("dashboard:home")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        return ctx


def profile(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
    return render(request, "accounts/profile.html", {"user": request.user})


# --- Account review interface ---
class AccountReviewListView(LoginRequiredMixin, View):
    """Supervisors/staff can see pending accounts."""

    def get(self, request):
        if not (request.user.is_staff or request.user.can_approve()):
            raise PermissionDenied("Only supervisors can review accounts.")
        pending = User.objects.filter(approval_status=User.ApprovalStatus.PENDING).exclude(username=request.user.username)
        return render(request, "accounts/account_review.html", {"pending_accounts": pending})


class AccountApproveView(LoginRequiredMixin, View):
    """Approve a pending account and assign the effective role."""

    def post(self, request, pk: int):
        if not (request.user.is_staff or request.user.can_approve()):
            raise PermissionDenied("Only supervisors can approve accounts.")
        account = get_object_or_404(User, pk=pk)
        if account.pk == request.user.pk:
            raise PermissionDenied("You cannot approve your own account.")
        if account.approval_status != User.ApprovalStatus.PENDING:
            messages.warning(request, "This account is not pending review.")
            return redirect("accounts:review")

        effective_role = request.POST.get("effective_role", account.requested_role)
        if effective_role not in dict(User.Role.choices):
            effective_role = User.Role.VIEWER

        account.role = effective_role
        account.approval_status = User.ApprovalStatus.APPROVED
        account.approved_by = request.user
        account.approved_at = timezone.now()
        account.is_active = True
        account.save()
        log_audit_event(
            actor=request.user,
            action="account:approve",
            target=account,
            metadata={"effective_role": effective_role, "approved_by": request.user.username},
        )
        messages.success(request, f"Account '{account.username}' approved as {account.get_role_display()}.")
        return redirect("accounts:review")


class AccountRejectView(LoginRequiredMixin, View):
    """Reject a pending account."""

    def post(self, request, pk: int):
        if not (request.user.is_staff or request.user.can_approve()):
            raise PermissionDenied("Only supervisors can reject accounts.")
        account = get_object_or_404(User, pk=pk)
        if account.pk == request.user.pk:
            raise PermissionDenied("You cannot reject your own account.")
        reason = request.POST.get("rejection_reason", "")
        account.approval_status = User.ApprovalStatus.REJECTED
        account.rejection_reason = reason
        account.is_active = False
        account.save()
        log_audit_event(
            actor=request.user,
            action="account:reject",
            target=account,
            metadata={"reason": reason[:200]},
        )
        messages.warning(request, f"Account '{account.username}' rejected.")
        return redirect("accounts:review")
