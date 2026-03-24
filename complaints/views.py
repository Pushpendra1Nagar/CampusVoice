from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.db.models import Count, Q
from decouple import config

from .models import Complaint, ComplaintUpvote
from .forms import ComplaintForm, AdminRemarkForm


def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def feed_view(request):
    complaints = Complaint.objects.annotate(upvote_count=Count('upvotes')).select_related('created_by')
    category = request.GET.get('category', '')
    status = request.GET.get('status', '')
    search = request.GET.get('q', '')
    if category:
        complaints = complaints.filter(category=category)
    if status:
        complaints = complaints.filter(status=status)
    if search:
        complaints = complaints.filter(Q(title__icontains=search) | Q(description__icontains=search))
    user_upvoted_ids = set()
    if request.user.is_authenticated:
        user_upvoted_ids = set(ComplaintUpvote.objects.filter(user=request.user).values_list('complaint_id', flat=True))
    return render(request, 'complaints/feed.html', {
        'complaints': complaints, 'user_upvoted_ids': user_upvoted_ids,
        'categories': Complaint.Category.choices, 'statuses': Complaint.Status.choices,
        'active_category': category, 'active_status': status, 'search_query': search,
    })


@login_required
def submit_complaint_view(request):
    form = ComplaintForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        complaint = form.save(commit=False)
        complaint.created_by = request.user
        complaint.save()
        messages.success(request, "Your complaint has been submitted anonymously!")
        return redirect('complaints:feed')
    return render(request, 'complaints/submit.html', {'form': form})


def complaint_detail_view(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk)
    is_owner = request.user.is_authenticated and complaint.created_by == request.user
    user_upvoted = request.user.is_authenticated and ComplaintUpvote.objects.filter(complaint=complaint, user=request.user).exists()
    return render(request, 'complaints/detail.html', {
        'complaint': complaint, 'is_owner': is_owner,
        'upvote_count': complaint.upvotes.count(), 'user_upvoted': user_upvoted,
    })


@login_required
def edit_complaint_view(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk, created_by=request.user)
    if complaint.status != 'pending':
        messages.error(request, "You can only edit pending complaints.")
        return redirect('complaints:my_complaints')
    form = ComplaintForm(request.POST or None, request.FILES or None, instance=complaint)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Complaint updated successfully!")
        return redirect('complaints:my_complaints')
    return render(request, 'complaints/edit.html', {'form': form, 'complaint': complaint})


@login_required
def delete_complaint_view(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk, created_by=request.user)
    if complaint.status != 'pending':
        messages.error(request, "You can only delete pending complaints.")
        return redirect('complaints:my_complaints')
    if request.method == 'POST':
        complaint.delete()
        messages.success(request, "Complaint deleted.")
        return redirect('complaints:my_complaints')
    return render(request, 'complaints/delete_confirm.html', {'complaint': complaint})


@login_required
def upvote_view(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    complaint = get_object_or_404(Complaint, pk=pk)
    if complaint.created_by == request.user:
        return JsonResponse({'error': 'Cannot upvote your own complaint'}, status=400)
    upvote, created = ComplaintUpvote.objects.get_or_create(complaint=complaint, user=request.user)
    if not created:
        upvote.delete()
        upvoted = False
    else:
        upvoted = True
    return JsonResponse({'upvoted': upvoted, 'count': complaint.upvotes.count()})


@login_required
def my_complaints_view(request):
    complaints = request.user.complaints.annotate(upvote_count=Count('upvotes')).order_by('-created_at')
    return render(request, 'complaints/my_complaints.html', {'complaints': complaints})


@login_required
@user_passes_test(is_admin, login_url='complaints:feed')
def admin_dashboard_view(request):
    complaints = Complaint.objects.annotate(upvote_count=Count('upvotes')).select_related('created_by').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    category_filter = request.GET.get('category', '')
    search = request.GET.get('q', '')
    if status_filter:
        complaints = complaints.filter(status=status_filter)
    if category_filter:
        complaints = complaints.filter(category=category_filter)
    if search:
        complaints = complaints.filter(Q(title__icontains=search) | Q(created_by__email__icontains=search) | Q(created_by__first_name__icontains=search))
    return render(request, 'complaints/admin_dashboard.html', {
        'complaints': complaints,
        'total': Complaint.objects.count(),
        'pending': Complaint.objects.filter(status='pending').count(),
        'in_progress': Complaint.objects.filter(status='in_progress').count(),
        'resolved': Complaint.objects.filter(status='resolved').count(),
        'rejected': Complaint.objects.filter(status='rejected').count(),
        'statuses': Complaint.Status.choices,
        'categories': Complaint.Category.choices,
        'active_status': status_filter,
        'active_category': category_filter,
        'search_query': search,
    })


@login_required
@user_passes_test(is_admin, login_url='complaints:feed')
def admin_update_complaint_view(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk)
    old_status = complaint.status
    form = AdminRemarkForm(request.POST or None, instance=complaint)
    if request.method == 'POST' and form.is_valid():
        updated = form.save()
        if updated.status != old_status:
            try:
                _notify_status_change(updated)
            except Exception as e:
                print(f"Email error: {e}")
        messages.success(request, f"Status updated to: {updated.get_status_display()}")
        return redirect('complaints:admin_dashboard')
    return render(request, 'complaints/admin_update.html', {'complaint': complaint, 'form': form})


def _notify_status_change(complaint):
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = config('BREVO_API_KEY')
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
    html_content = render_to_string('emails/status_update.html', {'complaint': complaint, 'student_name': complaint.created_by.first_name})
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": complaint.created_by.email}],
        sender={"name": "CampusVoice", "email": "campusvoice.cms@gmail.com"},
        subject=f"[CampusVoice] Complaint status: {complaint.get_status_display()}",
        html_content=html_content,
    )
    try:
        api_instance.send_transac_email(send_smtp_email)
    except ApiException as e:
        print(f"Brevo API error: {e}")


def trigger_escalation_view(request):
    """Called by a cron job or manually to escalate complaints."""
    from django.utils import timezone
    complaints = Complaint.objects.filter(
        status__in=['pending', 'in_progress'],
        escalation_level__lt=3
    )
    escalated = []
    for complaint in complaints:
        if complaint.should_escalate():
            old_level = complaint.escalation_level
            complaint.escalate()
            escalated.append(f"#{complaint.id} L{old_level}→L{complaint.escalation_level}")

    return JsonResponse({
        'escalated': escalated,
        'count': len(escalated),
        'checked_at': timezone.now().isoformat()
    })


# ─── Department User Dashboard ────────────────────────────────────────────────

@login_required
def staff_dashboard_view(request):
    """Redirects to correct dashboard based on role."""
    from users.models import Role
    role = request.user.role

    if role == Role.DEPT_USER:
        return dept_dashboard_view(request)
    elif role == Role.HOD:
        return hod_dashboard_view(request)
    elif role == Role.AUTHORITY:
        return authority_dashboard_view(request)
    elif request.user.is_staff or request.user.is_superuser:
        return admin_dashboard_view(request)
    else:
        messages.error(request, "You don't have staff access.")
        return redirect('complaints:feed')


@login_required
def dept_dashboard_view(request):
    """Level 1 — Department User sees complaints from their department at level 1."""
    from users.models import Role
    if request.user.role != Role.DEPT_USER:
        return redirect('complaints:feed')

    complaints = Complaint.objects.filter(
        escalation_level=1,
        created_by__department=request.user.department,
    ).annotate(upvote_count=Count('upvotes')).select_related('created_by').order_by('-created_at')

    status_filter = request.GET.get('status', '')
    if status_filter:
        complaints = complaints.filter(status=status_filter)

    return render(request, 'complaints/dept_dashboard.html', {
        'complaints': complaints,
        'total': complaints.count(),
        'pending': complaints.filter(status='pending').count(),
        'in_progress': complaints.filter(status='in_progress').count(),
        'resolved': complaints.filter(status='resolved').count(),
        'statuses': Complaint.Status.choices,
        'active_status': status_filter,
        'role_label': 'Department User',
        'department': request.user.department,
    })


@login_required
def hod_dashboard_view(request):
    """Level 2 — HOD sees complaints escalated to level 2 from their dept."""
    from users.models import Role
    if request.user.role != Role.HOD:
        return redirect('complaints:feed')

    complaints = Complaint.objects.filter(
        escalation_level=2,
        created_by__department=request.user.department,
    ).annotate(upvote_count=Count('upvotes')).select_related('created_by').order_by('-created_at')

    status_filter = request.GET.get('status', '')
    if status_filter:
        complaints = complaints.filter(status=status_filter)

    return render(request, 'complaints/dept_dashboard.html', {
        'complaints': complaints,
        'total': complaints.count(),
        'pending': complaints.filter(status='pending').count(),
        'in_progress': complaints.filter(status='in_progress').count(),
        'resolved': complaints.filter(status='resolved').count(),
        'statuses': Complaint.Status.choices,
        'active_status': status_filter,
        'role_label': 'HOD',
        'department': request.user.department,
    })


@login_required
def authority_dashboard_view(request):
    """Level 3 — Higher Authority sees all complaints escalated to level 3."""
    from users.models import Role
    if request.user.role != Role.AUTHORITY:
        return redirect('complaints:feed')

    complaints = Complaint.objects.filter(
        escalation_level=3,
    ).annotate(upvote_count=Count('upvotes')).select_related('created_by').order_by('-created_at')

    status_filter = request.GET.get('status', '')
    category_filter = request.GET.get('category', '')
    if status_filter:
        complaints = complaints.filter(status=status_filter)
    if category_filter:
        complaints = complaints.filter(category=category_filter)

    return render(request, 'complaints/dept_dashboard.html', {
        'complaints': complaints,
        'total': complaints.count(),
        'pending': complaints.filter(status='pending').count(),
        'in_progress': complaints.filter(status='in_progress').count(),
        'resolved': complaints.filter(status='resolved').count(),
        'statuses': Complaint.Status.choices,
        'categories': Complaint.Category.choices,
        'active_status': status_filter,
        'active_category': category_filter,
        'role_label': 'Higher Authority',
        'department': 'All Departments',
    })


@login_required
def staff_update_complaint_view(request, pk):
    """Dept/HOD/Authority can update status + add digital signature remark."""
    from users.models import Role
    from django.utils import timezone

    complaint = get_object_or_404(Complaint, pk=pk)

    # Access control — only correct level can update
    role = request.user.role
    if role == Role.DEPT_USER and complaint.escalation_level != 1:
        messages.error(request, "This complaint is not at your level.")
        return redirect('complaints:staff_dashboard')
    if role == Role.HOD and complaint.escalation_level != 2:
        messages.error(request, "This complaint is not at your level.")
        return redirect('complaints:staff_dashboard')
    if role == Role.AUTHORITY and complaint.escalation_level != 3:
        messages.error(request, "This complaint is not at your level.")
        return redirect('complaints:staff_dashboard')

    if request.method == 'POST':
        new_status = request.POST.get('status')
        remark = request.POST.get('admin_remark', '').strip()
        signature = request.POST.get('digital_signature', '').strip()

        if not signature:
            messages.error(request, "Digital signature is required to update a complaint.")
            return render(request, 'complaints/staff_update.html', {
                'complaint': complaint, 'statuses': Complaint.Status.choices
            })

        old_status = complaint.status
        complaint.status = new_status

        # Append signed remark with timestamp
        level_label = {
            Role.DEPT_USER: 'Dept. User',
            Role.HOD: 'HOD',
            Role.AUTHORITY: 'Higher Authority',
        }.get(role, 'Staff')

        timestamp = timezone.now().strftime('%d %b %Y %H:%M')
        signed_remark = (
            f"\n\n— [{level_label}] {request.user.get_full_name()} "
            f"| {timestamp}\n"
            f"Signature: {signature}\n"
            f"Action: Changed status to {dict(Complaint.Status.choices).get(new_status)}\n"
            f"Remark: {remark}"
        )
        complaint.admin_remark = (complaint.admin_remark or '') + signed_remark
        complaint.save()

        # Notify student
        if new_status != old_status:
            try:
                _notify_status_change(complaint)
            except Exception as e:
                print(f"Email error: {e}")

        messages.success(request, f"✅ Complaint updated and digitally signed.")
        return redirect('complaints:staff_dashboard')

    return render(request, 'complaints/staff_update.html', {
        'complaint': complaint,
        'statuses': Complaint.Status.choices,
    })