from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.template.loader import render_to_string
from django.conf import settings
from decouple import config
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import CustomUser, OTPCode
from .forms import RegistrationForm, OTPVerifyForm, LoginForm, ProfileUpdateForm


def register_view(request):
    if request.user.is_authenticated:
        return redirect('complaints:feed')

    form = RegistrationForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            request.session['pending_registration'] = {
                'email': form.cleaned_data['email'],
                'username': form.cleaned_data['username'],
                'first_name': form.cleaned_data['first_name'],
                'last_name': form.cleaned_data['last_name'],
                'password': form.cleaned_data['password1'],
                'roll_number': form.cleaned_data.get('roll_number', ''),
                'department': form.cleaned_data.get('department', ''),
                'year_of_study': form.cleaned_data.get('year_of_study'),
                'degree': form.cleaned_data.get('degree', ''),
            }

            # Rate limit check
            if not _check_otp_rate_limit(form.cleaned_data['email']):
                messages.error(request, "Too many OTP requests. Please wait 1 hour before trying again.")
                return render(request, 'users/register.html', {'form': form})

            otp = OTPCode.generate(form.cleaned_data['email'])
            try:
                _send_otp_email(form.cleaned_data['email'], otp.code)
                messages.success(request, f"OTP sent to {form.cleaned_data['email']}")
            except Exception as e:
                print(f"Email error: {e}")
                messages.warning(request, f"Account created but email failed. Your OTP is: {otp.code}")
            return redirect('users:verify_otp')
        else:
            # Show exactly what's wrong
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

    return render(request, 'users/register.html', {'form': form})


def verify_otp_view(request):
    """Step 2: Verify OTP and create the actual user account."""
    pending = request.session.get('pending_registration')
    if not pending:
        return redirect('users:register')

    form = OTPVerifyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        entered_code = form.cleaned_data['otp']
        otp_obj = OTPCode.objects.filter(
            email=pending['email'], code=entered_code, is_used=False
        ).first()

        if otp_obj and otp_obj.is_valid():
            otp_obj.is_used = True
            otp_obj.save()

            # Now create the verified user
            user = CustomUser.objects.create_user(
                email=pending['email'],
                username=pending['username'],
                first_name=pending['first_name'],
                last_name=pending['last_name'],
                password=pending['password'],
                roll_number=pending.get('roll_number'),
                department=pending.get('department', ''),
                year_of_study=pending.get('year_of_study'),
                degree=pending.get('degree', ''),
                is_email_verified=True,
            )
            del request.session['pending_registration']
            login(request, user)
            messages.success(request, f"Welcome to CampusVoice, {user.first_name}!")
            return redirect('complaints:feed')
        else:
            messages.error(request, "Invalid or expired OTP. Please try again.")

    return render(request, 'users/verify_otp.html', {
        'form': form,
        'email': pending['email']
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect('complaints:feed')

    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data['email'],
            password=form.cleaned_data['password'],
        )
        if user:
            login(request, user)
            next_url = request.GET.get('next', 'complaints:feed')
            return redirect(next_url)
        else:
            messages.error(request, "Invalid email or password.")

    return render(request, 'users/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('users:login')


@login_required
def profile_view(request):
    form = ProfileUpdateForm(
        request.POST or None,
        request.FILES or None,
        instance=request.user
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Profile updated successfully!")
        return redirect('users:profile')

    return render(request, 'users/profile.html', {
        'form': form,
        'complaint_count': request.user.complaints.count(),
        'resolved_count': request.user.complaints.filter(status='resolved').count(),
    })


def resend_otp_view(request):
    pending = request.session.get('pending_registration')
    if pending:
        if not _check_otp_rate_limit(pending['email']):
            messages.error(request, "Too many OTP requests. Please wait 1 hour.")
            return redirect('users:verify_otp')
        otp = OTPCode.generate(pending['email'])
        try:
            _send_otp_email(pending['email'], otp.code)
            messages.info(request, "New OTP sent to your email.")
        except Exception as e:
            messages.warning(request, f"Failed to send OTP. Your code: {otp.code}")
    return redirect('users:verify_otp')


# ─── Helper ─────────────────────────────────────────────────────────────────
def _send_otp_email(email, code):
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException

    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = config('BREVO_API_KEY')

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    html_content = render_to_string('emails/otp.html', {'code': code})

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": email}],
        sender={"name": "CampusVoice", "email": "campusvoice.cms@gmail.com"},
        subject="Your CampusVoice Verification Code",
        html_content=html_content,
    )

    try:
        api_instance.send_transac_email(send_smtp_email)
    except ApiException as e:
        print(f"Brevo API error: {e}")
        raise Exception("Failed to send OTP email")
    


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='complaints:feed')
def create_staff_view(request):
    import secrets
    import string

    ROLES = [
        ('dept_user', 'Department User'),
        ('hod', 'HOD'),
        ('authority', 'Higher Authority'),
        ('admin', 'System Admin'),
    ]

    from .models import Role
    recent_staff = CustomUser.objects.exclude(
        role=Role.STUDENT
    ).order_by('-date_joined')[:10]

    if request.method == 'POST':
        email      = request.POST.get('email', '').strip().lower()
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        role       = request.POST.get('role', '').strip()
        department = request.POST.get('department', '').strip()
        password   = request.POST.get('password', '').strip()

        errors = []
        if not email:
            errors.append("Email is required.")
        if not first_name:
            errors.append("First name is required.")
        if not role or role not in dict(ROLES):
            errors.append("Please select a valid role.")
        if not password or len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if CustomUser.objects.filter(email=email).exists():
            errors.append(f"A user with email '{email}' already exists.")

        base_username = email.split('@')[0]
        username = base_username
        counter = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'users/create_staff.html', {
                'roles': ROLES,
                'form_data': request.POST,
                'recent_staff': recent_staff,
            })

        try:
            user = CustomUser.objects.create_user(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password,
                role=role,
                department=department,
                is_email_verified=True,
                is_staff=(role == 'admin'),
            )
            from complaints.models import AuditLog
            AuditLog.log(
                performed_by=request.user,
                action_type='account_created',
                description=f"Created {role} account for {email} ({first_name} {last_name})",
                target_model='CustomUser',
                target_id=user.pk,
                request=request,
            )
        except Exception as e:
            messages.error(request, f"Failed to create user: {e}")
            return render(request, 'users/create_staff.html', {
                'roles': ROLES,
                'form_data': request.POST,
                'recent_staff': recent_staff,
            })

        try:
            _send_credentials_email(email, first_name, password, role)
            messages.success(request, f"✅ Account created for {email}. Credentials sent via email.")
        except Exception as e:
            messages.warning(request, f"Account created but email failed. Password: {password}")

        return redirect('users:create_staff')

    return render(request, 'users/create_staff.html', {
        'roles': ROLES,
        'recent_staff': recent_staff,
    })


def _send_credentials_email(email, name, password, role):
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException

    role_display = {
        'dept_user': 'Department User',
        'hod': 'Head of Department',
        'authority': 'Higher Authority',
        'admin': 'System Admin',
    }.get(role, role.title())

    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = config('BREVO_API_KEY')
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": email}],
        sender={"name": "CampusVoice", "email": "campusvoice.cms@gmail.com"},
        subject="Your CampusVoice Staff Account Credentials",
        html_content=f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:32px;border:1px solid #e2e5f0;">
          <h2 style="color:#2a52e8;">📣 CampusVoice Staff Account</h2>
          <p>Hi <strong>{name}</strong>, your account has been created.</p>
          <div style="background:#f0f2f9;border-radius:8px;padding:20px;margin:16px 0;">
            <p style="margin:6px 0;"><strong>Role:</strong> {role_display}</p>
            <p style="margin:6px 0;"><strong>Login Email:</strong> {email}</p>
            <p style="margin:6px 0;"><strong>Password:</strong> 
              <code style="background:#fff;padding:4px 10px;border-radius:6px;font-size:1.1rem;letter-spacing:2px;border:1px solid #ddd;">{password}</code>
            </p>
          </div>
          <p>Login at: <a href="https://campusvoice-bcw4.onrender.com/auth/login/">campusvoice-bcw4.onrender.com</a></p>
          <p style="color:#888;font-size:13px;">Please save your password — password reset is not available.</p>
        </div>
        """
    )
    try:
        api_instance.send_transac_email(send_smtp_email)
    except ApiException as e:
        print(f"Brevo error: {e}")
        raise Exception("Failed to send credentials email")


# ─── Password Reset ───────────────────────────────────────────────────────────

def password_reset_request_view(request):
    """Step 1: Student enters email to request reset link."""
    if request.user.is_authenticated:
        return redirect('complaints:feed')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        user  = CustomUser.objects.filter(email=email, is_active=True).first()

        # Always show same message to prevent email enumeration
        if user:
            # Generate reset OTP and store in session
            otp = OTPCode.generate(email)
            try:
                _send_password_reset_email(email, user.first_name, otp.code)
            except Exception as e:
                print(f"Reset email error: {e}")

        messages.success(
            request,
            "If that email is registered, you will receive a reset code shortly."
        )
        request.session['reset_email'] = email
        return redirect('users:password_reset_verify')

    return render(request, 'users/password_reset.html')


def password_reset_verify_view(request):
    """Step 2: Enter OTP + new password."""
    email = request.session.get('reset_email')
    if not email:
        return redirect('users:password_reset')

    if request.method == 'POST':
        otp_code     = request.POST.get('otp', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_pwd  = request.POST.get('confirm_password', '').strip()

        if not new_password or len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters.")
            return render(request, 'users/password_reset_confirm.html', {'email': email})

        if new_password != confirm_pwd:
            messages.error(request, "Passwords do not match.")
            return render(request, 'users/password_reset_confirm.html', {'email': email})

        otp_obj = OTPCode.objects.filter(
            email=email, code=otp_code, is_used=False
        ).first()

        if not otp_obj or not otp_obj.is_valid():
            messages.error(request, "Invalid or expired code. Please request a new one.")
            return render(request, 'users/password_reset_confirm.html', {'email': email})

        user = CustomUser.objects.filter(email=email).first()
        if user:
            user.set_password(new_password)
            user.save()
            otp_obj.is_used = True
            otp_obj.save()
            del request.session['reset_email']
            messages.success(request, "Password reset successfully! Please login.")
            return redirect('users:login')
        else:
            messages.error(request, "User not found.")

    return render(request, 'users/password_reset_confirm.html', {'email': email})


# ─── Change Password (for logged-in users) ────────────────────────────────────

@login_required
def change_password_view(request):
    if request.method == 'POST':
        current_password = request.POST.get('current_password', '')
        new_password     = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not request.user.check_password(current_password):
            messages.error(request, "Current password is incorrect.")
            return render(request, 'users/change_password.html')

        if len(new_password) < 8:
            messages.error(request, "New password must be at least 8 characters.")
            return render(request, 'users/change_password.html')

        if new_password != confirm_password:
            messages.error(request, "New passwords do not match.")
            return render(request, 'users/change_password.html')

        if current_password == new_password:
            messages.error(request, "New password must be different from current password.")
            return render(request, 'users/change_password.html')

        request.user.set_password(new_password)
        request.user.save()

        # Keep user logged in after password change
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, request.user)

        messages.success(request, "✅ Password changed successfully!")
        return redirect('users:profile')

    return render(request, 'users/change_password.html')


# ─── Manage Staff ─────────────────────────────────────────────────────────────

@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='complaints:feed')
def manage_staff_view(request):
    from .models import Role
    staff_users = CustomUser.objects.exclude(
        role=Role.STUDENT
    ).order_by('role', 'department', 'first_name')

    return render(request, 'users/manage_staff.html', {
        'staff_users': staff_users,
        'roles': Role.choices,
    })


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='complaints:feed')
def deactivate_staff_view(request, pk):
    from .models import Role
    user = get_object_or_404(CustomUser, pk=pk)

    from complaints.models import AuditLog
    action = 'account_deactivated' if user.is_active else 'account_reactivated'
    AuditLog.log(
        performed_by=request.user,
        action_type=action,
        description=f"{'Deactivated' if user.is_active else 'Reactivated'} account: {user.get_full_name()} ({user.email})",
        target_model='CustomUser',
        target_id=user.pk,
        request=request,
    )

    # Prevent admin from deactivating themselves
    if user == request.user:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect('users:manage_staff')

    if user.role == Role.STUDENT:
        messages.error(request, "Use this only for staff accounts.")
        return redirect('users:manage_staff')

    if request.method == 'POST':
        if user.is_active:
            user.is_active = False
            user.save()
            messages.success(request, f"{user.get_full_name()} has been deactivated.")
        else:
            user.is_active = True
            user.save()
            messages.success(request, f"{user.get_full_name()} has been reactivated.")

    return redirect('users:manage_staff')


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='complaints:feed')
def delete_staff_view(request, pk):
    from .models import Role
    user = get_object_or_404(CustomUser, pk=pk)

    if user == request.user:
        messages.error(request, "You cannot delete your own account.")
        return redirect('users:manage_staff')

    if user.role == Role.STUDENT:
        messages.error(request, "Use this only for staff accounts.")
        return redirect('users:manage_staff')

    if request.method == 'POST':
        name = user.get_full_name()
        from complaints.models import AuditLog
        AuditLog.log(
            performed_by=request.user,
            action_type='account_deleted',
            description=f"Deleted {user.role} account: {user.get_full_name()} ({user.email})",
            target_model='CustomUser',
            request=request,
        )
        user.delete()
        messages.success(request, f"Account for {name} has been permanently deleted.")
        return redirect('users:manage_staff')

    return render(request, 'users/delete_staff_confirm.html', {'staff_user': user})


# ─── OTP rate limit helper ────────────────────────────────────────────────────

def _check_otp_rate_limit(email):
    """Returns True if allowed, False if rate limited (max 3 per hour)."""
    from django.core.cache import cache
    key   = f"otp_count_{email.replace('@','_').replace('.','_')}"
    count = cache.get(key, 0)
    if count >= 3:
        return False
    cache.set(key, count + 1, timeout=3600)  # 1 hour window
    return True


def _send_password_reset_email(email, name, code):
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = config('BREVO_API_KEY')
    api_instance   = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )
    html_content = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:32px;border:1px solid #e2e5f0;">
      <h2 style="color:#2a52e8;">🔐 Password Reset — CampusVoice</h2>
      <p>Hi <strong>{name}</strong>, here is your password reset code:</p>
      <div style="background:#f0f2f9;border-radius:12px;padding:24px;text-align:center;margin:20px 0;">
        <div style="font-size:42px;font-weight:700;letter-spacing:12px;color:#2a52e8;font-family:monospace;">{code}</div>
        <div style="color:#888;font-size:13px;margin-top:8px;">Valid for 10 minutes only</div>
      </div>
      <p style="color:#888;font-size:13px;">If you did not request a password reset, ignore this email.</p>
    </div>
    """
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": email}],
        sender={"name": "CampusVoice", "email": "campusvoice.cms@gmail.com"},
        subject="[CampusVoice] Password Reset Code",
        html_content=html_content,
    )
    try:
        api_instance.send_transac_email(send_smtp_email)
    except ApiException as e:
        print(f"Reset email error: {e}")
        raise