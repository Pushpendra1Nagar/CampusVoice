from django.shortcuts import render, redirect
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
    """Resend OTP to the pending email."""
    pending = request.session.get('pending_registration')
    if pending:
        otp = OTPCode.generate(pending['email'])
        _send_otp_email(pending['email'], otp.code)
        messages.info(request, "New OTP sent to your email.")
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

    if request.method == 'POST':
        email      = request.POST.get('email', '').strip().lower()
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        role       = request.POST.get('role', '').strip()

        # ── Validation ──────────────────────────────────────────────
        errors = []
        if not email:
            errors.append("Email is required.")
        if not first_name:
            errors.append("First name is required.")
        if not role or role not in dict(ROLES):
            errors.append("Please select a valid role.")
        if CustomUser.objects.filter(email=email).exists():
            errors.append(f"A user with email '{email}' already exists.")

        # Unique username
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
            })

        # ── Create user ─────────────────────────────────────────────
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for _ in range(10))

        try:
            user = CustomUser.objects.create_user(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password,
                role=role,
                is_email_verified=True,
                is_staff=(role == 'admin'),
            )
        except Exception as e:
            messages.error(request, f"Failed to create user: {e}")
            return render(request, 'users/create_staff.html', {
                'roles': ROLES,
                'form_data': request.POST,
            })

        # ── Send credentials email ───────────────────────────────────
        try:
            _send_credentials_email(email, first_name, password, role)
            messages.success(request, f"Account created for {email} and credentials sent via email.")
        except Exception as e:
            messages.warning(
                request,
                f"Account created for {email} but email failed to send. "
                f"Temporary password: {password}"
            )

        return redirect('users:create_staff')

    return render(request, 'users/create_staff.html', {
        'roles': ROLES,
    })


def _send_credentials_email(email, name, password, role):
    from django.core.mail import send_mail
    from django.conf import settings

    role_display = dict([
        ('dept_user', 'Department User'),
        ('hod', 'Head of Department'),
        ('authority', 'Higher Authority'),
        ('admin', 'System Admin'),
    ]).get(role, role.title())

    subject = "Your CampusVoice Staff Account Credentials"
    message = f"""Hi {name},

Your CampusVoice staff account has been created.

  Role      : {role_display}
  Email     : {email}
  Password  : {password}

Please log in and change your password immediately.

Regards,
CampusVoice Team
"""
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )



