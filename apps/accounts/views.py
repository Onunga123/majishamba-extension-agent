"""Views for the accounts app — registration, login, account review."""
from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django import forms
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_http_methods

from apps.audit.service import log_audit_event

from .models import User
from .permissions import require_system_admin


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
            ("extension_officer", "Extension Officer"),
            ("supervisor", "Supervisor"),
            ("viewer", "Viewer"),
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
        user.is_active = False  # Cannot authenticate until admin approval
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user


class AdminCreateUserForm(forms.ModelForm):
    """Form used by a system administrator to provision an approved account."""

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "auth-input"}),
        help_text="At least 10 characters.",
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "auth-input"}),
    )
    role = forms.ChoiceField(
        label="Role",
        choices=User.Role.choices,
        widget=forms.Select(attrs={"class": "auth-input"}),
        help_text="The account is approved immediately with this role.",
    )

    class Meta:
        model = User
        fields = ["full_name", "username", "email", "role", "organization", "sub_county", "ward"]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "auth-input"}),
            "username": forms.TextInput(attrs={"class": "auth-input"}),
            "email": forms.EmailInput(attrs={"class": "auth-input"}),
            "organization": forms.TextInput(attrs={"class": "auth-input"}),
            "sub_county": forms.TextInput(attrs={"class": "auth-input"}),
            "ward": forms.TextInput(attrs={"class": "auth-input"}),
        }

    def clean_password2(self):
        password = self.cleaned_data.get("password1")
        confirmation = self.cleaned_data.get("password2")
        if password and password != confirmation:
            raise forms.ValidationError("Passwords do not match.")
        if password and len(password) < 10:
            raise forms.ValidationError("Password must be at least 10 characters.")
        return confirmation

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.requested_role = user.role
        user.approval_status = User.ApprovalStatus.APPROVED
        user.is_active = True
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

    def form_invalid(self, form):
        """Override to show a specific message for pending accounts whose
        credentials are valid, without disclosing account existence for
        invalid credentials or non-pending accounts.
        """
        # form.cleaned_data is empty when the form is invalid — use form.data
        # (the raw POST QueryDict) to get the submitted username and password.
        username = form.data.get("username", "")
        password = form.data.get("password", "")
        if username and password:
            try:
                user = User.objects.get(username=username)
                # Only show the pending message if the password is correct —
                # this ensures we don't reveal account existence for someone
                # who hasn't supplied valid credentials.
                if user.check_password(password):
                    if user.approval_status == User.ApprovalStatus.PENDING:
                        form.add_error(None, (
                            "Your account is awaiting administrator approval. "
                            "You can sign in once your account has been approved."
                        ))
                    # For rejected/suspended accounts, fall through to the
                    # generic "check your username and password" message.
                    # We do NOT disclose that the account was rejected.
            except User.DoesNotExist:
                pass  # Generic error — do not disclose username existence
        return super().form_invalid(form)


@login_required
@require_http_methods(["GET"])
def profile(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
    """Display the authenticated user's own profile.

    Phase C security:
      - ``@login_required`` redirects anonymous users to /accounts/login/
        (302), so the template never renders for an unauthenticated request.
      - ``@require_http_methods(["GET"])`` rejects POST/PUT/PATCH/DELETE with
        HTTP 405. The profile page is read-only; no mutation path exists.
      - The view only ever uses ``request.user`` (never a URL parameter), so
        there is no way to view or edit another user's profile through this
        endpoint.
    """
    return render(request, "accounts/profile.html", {"user": request.user})


# --- Account review interface ---
class AccountReviewListView(LoginRequiredMixin, View):
    """Approved system administrators can see pending accounts."""

    def get(self, request):
        require_system_admin(request.user)
        pending = User.objects.filter(approval_status=User.ApprovalStatus.PENDING).exclude(username=request.user.username)
        return render(request, "accounts/account_review.html", {"pending_accounts": pending})


class AdminCreateUserView(LoginRequiredMixin, View):
    """Allow only an approved system administrator to provision an account."""

    def get(self, request):
        require_system_admin(request.user)
        return render(request, "accounts/create_user.html", {"form": AdminCreateUserForm()})

    def post(self, request):
        require_system_admin(request.user)
        form = AdminCreateUserForm(request.POST)
        if not form.is_valid():
            return render(request, "accounts/create_user.html", {"form": form})

        with transaction.atomic():
            user = form.save(commit=False)
            user.approved_by = request.user
            user.approved_at = timezone.now()
            user.save()
        log_audit_event(
            actor=request.user,
            action="account:create_by_admin",
            target=user,
            metadata={"role": user.role, "created_by": request.user.username},
        )
        messages.success(request, f"Account '{user.username}' created as {user.get_role_display()}.")
        return redirect("accounts:review")


class AccountApproveView(LoginRequiredMixin, View):
    """Approve a pending account and assign the effective role."""

    def post(self, request, pk: int):
        require_system_admin(request.user)
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
        require_system_admin(request.user)
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
