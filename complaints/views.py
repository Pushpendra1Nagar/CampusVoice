from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.db.models import Count, Q
from django.utils import timezone
from decouple import config
from django.db.models.functions import TruncWeek, TruncDate
from django.db.models import Avg, F, ExpressionWrapper, DurationField
import json
from .models import Complaint, ComplaintUpvote, ComplaintUpdate, ComplaintMessage
from .forms import ComplaintForm, AdminRemarkForm


def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


# ─── Feed ─────────────────────────────────────────────────────────────────────

def feed_view(request):
    category = request.GET.get('category', '')
    status   = request.GET.get('status', '')
    search   = request.GET.get('q', '')

    base = Complaint.objects.annotate(
        upvote_count=Count('upvotes')
    ).select_related('created_by')

    if category:
        base = base.filter(category=category)
    if search:
        base = base.filter(
            Q(title__icontains=search) | Q(description__icontains=search)
        )

    if status:
        active_complaints   = None
        resolved_complaints = None
        complaints          = base.filter(status=status).order_by('-created_at')
    else:
        complaints          = None
        active_complaints   = base.filter(
            status__in=['pending', 'in_progress']
        ).order_by('-created_at')
        resolved_complaints = base.filter(
            status='resolved'
        ).order_by('-updated_at')

    user_upvoted_ids = set()
    if request.user.is_authenticated:
        user_upvoted_ids = set(
            ComplaintUpvote.objects.filter(user=request.user)
            .values_list('complaint_id', flat=True)
        )

    return render(request, 'complaints/feed.html', {
        'complaints':          complaints,
        'active_complaints':   active_complaints,
        'resolved_complaints': resolved_complaints,
        'user_upvoted_ids':    user_upvoted_ids,
        'categories':          Complaint.Category.choices,
        'statuses':            Complaint.Status.choices,
        'active_category':     category,
        'active_status':       status,
        'search_query':        search,
        'active_count':   active_complaints.count()   if active_complaints   is not None else 0,
        'resolved_count': resolved_complaints.count() if resolved_complaints is not None else 0,
    })


# ─── Student Dashboard ────────────────────────────────────────────────────────

@login_required
def student_dashboard_view(request):
    from users.models import Role
    # Redirect staff to their own dashboards
    if request.user.role != Role.STUDENT and not request.user.is_superuser:
        return redirect('complaints:staff_dashboard')

    my_complaints = request.user.complaints.annotate(
        upvote_count=Count('upvotes')
    ).order_by('-created_at')

    total      = my_complaints.count()
    pending    = my_complaints.filter(status='pending').count()
    in_prog    = my_complaints.filter(status='in_progress').count()
    resolved   = my_complaints.filter(status='resolved').count()
    escalated  = my_complaints.filter(escalation_level__gt=1).count()

    # Recent activity — last 5 complaints with recent updates
    recent = my_complaints[:5]

    # Unread staff messages
    unread_messages = ComplaintMessage.objects.filter(
        complaint__created_by=request.user,
        sender_type='staff',
        is_read=False
    ).count()

    return render(request, 'complaints/student_dashboard.html', {
        'my_complaints':   my_complaints,
        'total':           total,
        'pending':         pending,
        'in_progress':     in_prog,
        'resolved':        resolved,
        'escalated':       escalated,
        'recent':          recent,
        'unread_messages': unread_messages,
        'stats': [
            ('Total',       total,     'var(--accent)'),
            ('Pending',     pending,   'var(--warning)'),
            ('In Progress', in_prog,   'var(--info)'),
            ('Resolved',    resolved,  'var(--success)'),
            ('Escalated',   escalated, 'var(--danger)'),
        ],
    })


# ─── Submit ───────────────────────────────────────────────────────────────────

@login_required
def submit_complaint_view(request):
    form = ComplaintForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        complaint = form.save(commit=False)
        complaint.created_by = request.user
        complaint.save()
        # Redirect to success page with complaint ID
        return redirect('complaints:submit_success', pk=complaint.pk)
    return render(request, 'complaints/submit.html', {'form': form})


@login_required
def submit_success_view(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk, created_by=request.user)
    return render(request, 'complaints/submit_success.html', {'complaint': complaint})


# ─── Public Complaint Tracker ─────────────────────────────────────────────────

def complaint_tracker_view(request):
    """Anyone can track a complaint by ID — no login needed."""
    complaint = None
    error     = None
    complaint_id = request.GET.get('id', '').strip()

    if complaint_id:
        try:
            complaint = Complaint.objects.get(pk=int(complaint_id))
        except (Complaint.DoesNotExist, ValueError):
            error = f"No complaint found with ID #{complaint_id}."

    return render(request, 'complaints/track.html', {
        'complaint':    complaint,
        'complaint_id': complaint_id,
        'error':        error,
    })


# ─── Detail ───────────────────────────────────────────────────────────────────

def complaint_detail_view(request, pk):
    complaint    = get_object_or_404(Complaint, pk=pk)
    is_owner     = request.user.is_authenticated and complaint.created_by == request.user
    user_upvoted = (
        request.user.is_authenticated and
        ComplaintUpvote.objects.filter(complaint=complaint, user=request.user).exists()
    )
    updates  = complaint.updates.all()
    messages_thread = complaint.messages.all()

    # Mark staff messages as read when owner views
    if is_owner:
        complaint.messages.filter(sender_type='staff', is_read=False).update(is_read=True)

    return render(request, 'complaints/detail.html', {
        'complaint':        complaint,
        'is_owner':         is_owner,
        'upvote_count':     complaint.upvotes.count(),
        'user_upvoted':     user_upvoted,
        'updates':          updates,
        'messages_thread':  messages_thread,
    })


# ─── Student Add Follow-up Update ────────────────────────────────────────────

@login_required
def add_update_view(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk, created_by=request.user)

    if complaint.status in ['resolved', 'rejected', 'withdrawn']:
        messages.error(request, "Cannot add updates to a closed complaint.")
        return redirect('complaints:my_complaints')

    if request.method == 'POST':
        content = request.POST.get('content', '').strip()
        if not content:
            messages.error(request, "Update content cannot be empty.")
        elif len(content) > 1000:
            messages.error(request, "Update too long. Maximum 1000 characters.")
        else:
            ComplaintUpdate.objects.create(
                complaint=complaint,
                added_by=request.user,
                content=content,
            )
            # Notify staff about the update
            try:
                _notify_student_update(complaint, content)
            except Exception as e:
                print(f"Update notify error: {e}")

            messages.success(request, "✅ Your update has been added.")
            return redirect('complaints:detail', pk=pk)

    return render(request, 'complaints/add_update.html', {'complaint': complaint})


# ─── Student Withdraw Complaint ───────────────────────────────────────────────

@login_required
def withdraw_complaint_view(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk, created_by=request.user)

    if complaint.status in ['resolved', 'rejected']:
        messages.error(request, "This complaint is already closed.")
        return redirect('complaints:my_complaints')

    if complaint.status == 'withdrawn':
        messages.error(request, "This complaint is already withdrawn.")
        return redirect('complaints:my_complaints')

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        complaint.status = 'withdrawn'
        complaint.admin_remark = (complaint.admin_remark or '') + (
            f"\n\n— [Student Withdrawal] {timezone.now().strftime('%d %b %Y %H:%M')}\n"
            f"Reason: {reason or 'No reason provided'}"
        )
        complaint.save()
        messages.success(request, "Your complaint has been withdrawn.")
        return redirect('complaints:my_complaints')

    return render(request, 'complaints/withdraw_confirm.html', {'complaint': complaint})


# ─── Staff Ask for More Info ──────────────────────────────────────────────────

@login_required
def staff_ask_view(request, pk):
    """Staff sends a question to the student."""
    from users.models import Role
    complaint = get_object_or_404(Complaint, pk=pk)
    role      = request.user.role

    # Only staff can ask
    allowed = (
        request.user.is_staff or
        request.user.is_superuser or
        role in [Role.DEPT_USER, Role.HOD, Role.AUTHORITY]
    )
    if not allowed:
        return redirect('complaints:feed')

    if request.method == 'POST':
        message_text = request.POST.get('message', '').strip()
        if not message_text:
            messages.error(request, "Message cannot be empty.")
        else:
            ComplaintMessage.objects.create(
                complaint=complaint,
                sender=request.user,
                sender_type='staff',
                message=message_text,
            )
            try:
                _notify_staff_question(complaint, message_text, request.user)
            except Exception as e:
                print(f"Staff ask notify error: {e}")

            messages.success(request, "✅ Question sent to student.")
            return redirect('complaints:staff_dashboard')

    return render(request, 'complaints/staff_ask.html', {'complaint': complaint})


# ─── Student Reply to Staff ───────────────────────────────────────────────────

@login_required
def student_reply_view(request, pk):
    complaint = get_object_or_404(Complaint, pk=pk, created_by=request.user)

    if request.method == 'POST':
        reply_text = request.POST.get('message', '').strip()
        if not reply_text:
            messages.error(request, "Reply cannot be empty.")
        else:
            ComplaintMessage.objects.create(
                complaint=complaint,
                sender=request.user,
                sender_type='student',
                message=reply_text,
            )
            messages.success(request, "✅ Reply sent.")
            return redirect('complaints:detail', pk=pk)

    return redirect('complaints:detail', pk=pk)


# ─── Edit / Delete ────────────────────────────────────────────────────────────

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


# ─── Upvote ───────────────────────────────────────────────────────────────────

@login_required
def upvote_view(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    complaint = get_object_or_404(Complaint, pk=pk)
    if complaint.created_by == request.user:
        return JsonResponse({'error': 'Cannot upvote your own complaint'}, status=400)
    upvote, created = ComplaintUpvote.objects.get_or_create(
        complaint=complaint, user=request.user
    )
    if not created:
        upvote.delete()
        upvoted = False
    else:
        upvoted = True
    return JsonResponse({'upvoted': upvoted, 'count': complaint.upvotes.count()})


# ─── My Complaints ────────────────────────────────────────────────────────────

@login_required
def my_complaints_view(request):
    complaints = request.user.complaints.annotate(
        upvote_count=Count('upvotes')
    ).order_by('-created_at')
    return render(request, 'complaints/my_complaints.html', {'complaints': complaints})


# ─── Admin Dashboard ──────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_admin, login_url='complaints:feed')
def admin_dashboard_view(request):
    complaints = Complaint.objects.annotate(
        upvote_count=Count('upvotes')
    ).select_related('created_by').order_by('-created_at')

    status_filter   = request.GET.get('status', '')
    category_filter = request.GET.get('category', '')
    search          = request.GET.get('q', '')

    if status_filter:
        complaints = complaints.filter(status=status_filter)
    if category_filter:
        complaints = complaints.filter(category=category_filter)
    if search:
        complaints = complaints.filter(
            Q(title__icontains=search) |
            Q(created_by__email__icontains=search) |
            Q(created_by__first_name__icontains=search)
        )

    return render(request, 'complaints/admin_dashboard.html', {
        'complaints':      complaints,
        'total':           Complaint.objects.count(),
        'pending':         Complaint.objects.filter(status='pending').count(),
        'in_progress':     Complaint.objects.filter(status='in_progress').count(),
        'resolved':        Complaint.objects.filter(status='resolved').count(),
        'rejected':        Complaint.objects.filter(status='rejected').count(),
        'statuses':        Complaint.Status.choices,
        'categories':      Complaint.Category.choices,
        'active_status':   status_filter,
        'active_category': category_filter,
        'search_query':    search,
    })

@login_required
@user_passes_test(is_admin, login_url='complaints:feed')
def admin_update_complaint_view(request, pk):
    complaint  = get_object_or_404(Complaint, pk=pk)
    old_status = complaint.status
    form       = AdminRemarkForm(request.POST or None, instance=complaint)

    if request.method == 'POST' and form.is_valid():
        remark = form.cleaned_data.get('admin_remark', '').strip()

        # ── Sanitize: strip any Django template tags ──────────────────
        if '{%' in remark or '{{' in remark or '%}' in remark or '}}' in remark:
            messages.error(
                request,
                "⚠️ Remark contains invalid characters. "
                "Please remove any { % or {{ characters."
            )
            return render(request, 'complaints/admin_update.html', {
                'complaint': complaint,
                'form':      form,
            })

        updated = form.save()

        if updated.status != old_status:
            try:
                _notify_status_change(updated)
            except Exception as e:
                print(f"Email error: {e}")

        messages.success(
            request,
            f"✅ Status updated to: {updated.get_status_display()}"
        )
        return redirect('complaints:admin_dashboard')

    return render(request, 'complaints/admin_update.html', {
        'complaint': complaint,
        'form':      form,
    })

# ─── Staff Dashboards ─────────────────────────────────────────────────────────

@login_required
def staff_dashboard_view(request):
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
    from users.models import Role
    if request.user.role != Role.DEPT_USER:
        return redirect('complaints:feed')
    complaints = Complaint.objects.filter(
        created_by__department=request.user.department,
    ).annotate(upvote_count=Count('upvotes')).select_related('created_by').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    if status_filter:
        complaints = complaints.filter(status=status_filter)
    return render(request, 'complaints/dept_dashboard.html', {
        'complaints':    complaints,
        'total':         complaints.count(),
        'pending':       complaints.filter(status='pending').count(),
        'in_progress':   complaints.filter(status='in_progress').count(),
        'resolved':      complaints.filter(status='resolved').count(),
        'statuses':      Complaint.Status.choices,
        'active_status': status_filter,
        'role_label':    'Department User',
        'department':    request.user.department,
    })


@login_required
def hod_dashboard_view(request):
    from users.models import Role
    if request.user.role != Role.HOD:
        return redirect('complaints:feed')
    complaints = Complaint.objects.filter(
        escalation_level__gte=2,
        created_by__department=request.user.department,
    ).annotate(upvote_count=Count('upvotes')).select_related('created_by').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    if status_filter:
        complaints = complaints.filter(status=status_filter)
    return render(request, 'complaints/dept_dashboard.html', {
        'complaints':    complaints,
        'total':         complaints.count(),
        'pending':       complaints.filter(status='pending').count(),
        'in_progress':   complaints.filter(status='in_progress').count(),
        'resolved':      complaints.filter(status='resolved').count(),
        'statuses':      Complaint.Status.choices,
        'active_status': status_filter,
        'role_label':    'HOD',
        'department':    request.user.department,
    })


@login_required
def authority_dashboard_view(request):
    from users.models import Role
    if request.user.role != Role.AUTHORITY:
        return redirect('complaints:feed')
    complaints = Complaint.objects.filter(
        escalation_level__gte=3,
    ).annotate(upvote_count=Count('upvotes')).select_related('created_by').order_by('-created_at')
    status_filter   = request.GET.get('status', '')
    category_filter = request.GET.get('category', '')
    if status_filter:
        complaints = complaints.filter(status=status_filter)
    if category_filter:
        complaints = complaints.filter(category=category_filter)
    return render(request, 'complaints/dept_dashboard.html', {
        'complaints':      complaints,
        'total':           complaints.count(),
        'pending':         complaints.filter(status='pending').count(),
        'in_progress':     complaints.filter(status='in_progress').count(),
        'resolved':        complaints.filter(status='resolved').count(),
        'statuses':        Complaint.Status.choices,
        'categories':      Complaint.Category.choices,
        'active_status':   status_filter,
        'active_category': category_filter,
        'role_label':      'Higher Authority',
        'department':      'All Departments',
    })


@login_required
def staff_update_complaint_view(request, pk):
    from users.models import Role
    complaint = get_object_or_404(Complaint, pk=pk)
    role      = request.user.role

    # ── Access control ────────────────────────────────────────────────
    if role == Role.DEPT_USER:
        if complaint.created_by.department != request.user.department:
            messages.error(request, "This complaint is not from your department.")
            return redirect('complaints:staff_dashboard')
    elif role == Role.HOD:
        if complaint.created_by.department != request.user.department:
            messages.error(request, "This complaint is not from your department.")
            return redirect('complaints:staff_dashboard')

    if request.method == 'POST':
        new_status = request.POST.get('status')
        remark     = request.POST.get('admin_remark', '').strip()
        signature  = request.POST.get('digital_signature', '').strip()

        # ── Validate signature ────────────────────────────────────────
        if not signature:
            messages.error(request, "Digital signature is required.")
            return render(request, 'complaints/staff_update.html', {
                'complaint': complaint,
                'statuses':  Complaint.Status.choices,
            })

        # ── Sanitize remark ───────────────────────────────────────────
        if '{%' in remark or '{{' in remark or '%}' in remark or '}}' in remark:
            messages.error(
                request,
                "⚠️ Remark contains invalid characters. "
                "Please remove any { % or {{ characters."
            )
            return render(request, 'complaints/staff_update.html', {
                'complaint': complaint,
                'statuses':  Complaint.Status.choices,
            })

        # ── Sanitize signature ────────────────────────────────────────
        if '{%' in signature or '{{' in signature:
            messages.error(request, "⚠️ Invalid signature.")
            return render(request, 'complaints/staff_update.html', {
                'complaint': complaint,
                'statuses':  Complaint.Status.choices,
            })

        # ── Build signed remark ───────────────────────────────────────
        old_status = complaint.status
        complaint.status = new_status

        level_label = {
            Role.DEPT_USER: 'Dept. User',
            Role.HOD:       'HOD',
            Role.AUTHORITY: 'Higher Authority',
        }.get(role, 'Staff')

        timestamp = timezone.now().strftime('%d %b %Y %H:%M')
        signed_remark = (
            f"\n\n— [{level_label}] {request.user.get_full_name()} "
            f"| {timestamp}\n"
            f"Signature: {signature}\n"
            f"Action: Changed to "
            f"{dict(Complaint.Status.choices).get(new_status, new_status)}\n"
            f"Remark: {remark}"
        )
        complaint.admin_remark = (complaint.admin_remark or '') + signed_remark
        complaint.save()

        # ── Notify student ────────────────────────────────────────────
        if new_status != old_status:
            try:
                _notify_status_change(complaint)
            except Exception as e:
                print(f"Email error: {e}")

        messages.success(request, "✅ Complaint updated and digitally signed.")
        return redirect('complaints:staff_dashboard')

    return render(request, 'complaints/staff_update.html', {
        'complaint': complaint,
        'statuses':  Complaint.Status.choices,
    })

# ─── Escalation ───────────────────────────────────────────────────────────────

def trigger_escalation_view(request):
    complaints = Complaint.objects.filter(
        status__in=['pending', 'in_progress'],
        escalation_level__lt=3
    )
    escalated = []
    for complaint in complaints:
        if complaint.should_escalate():
            old_level = complaint.escalation_level
            complaint.escalate()
            try:
                _notify_escalation(complaint)
            except Exception as e:
                print(f"Escalation email error: {e}")
            escalated.append(f"#{complaint.id} L{old_level}→L{complaint.escalation_level}")

    return JsonResponse({
        'escalated':  escalated,
        'count':      len(escalated),
        'checked_at': timezone.now().isoformat()
    })


# ─── Admin Analytics Dashboard ───────────────────────────────────────────────

@login_required
@user_passes_test(is_admin, login_url='complaints:feed')
def analytics_view(request):
    from django.utils import timezone
    import datetime

    # Date range filter
    range_filter = request.GET.get('range', '30')
    try:
        days = int(range_filter)
    except ValueError:
        days = 30
    since = timezone.now() - datetime.timedelta(days=days)

    all_complaints = Complaint.objects.filter(created_at__gte=since)

    # ── Complaints per category ─────────────────────────────────────────
    cat_data = {}
    for val, label in Complaint.Category.choices:
        cat_data[label] = all_complaints.filter(category=val).count()

    # ── Complaints per department ───────────────────────────────────────
    dept_data = {}
    depts = all_complaints.values_list(
        'created_by__department', flat=True
    ).distinct()
    for dept in depts:
        if dept:
            dept_data[dept] = all_complaints.filter(
                created_by__department=dept
            ).count()

    # ── Status breakdown ────────────────────────────────────────────────
    status_data = {}
    for val, label in Complaint.Status.choices:
        status_data[label] = all_complaints.filter(status=val).count()

    # ── Complaints per week (last 8 weeks) ──────────────────────────────
    eight_weeks_ago = timezone.now() - datetime.timedelta(weeks=8)
    weekly_qs = (
        Complaint.objects
        .filter(created_at__gte=eight_weeks_ago)
        .annotate(week=TruncWeek('created_at'))
        .values('week')
        .annotate(count=Count('id'))
        .order_by('week')
    )
    weekly_labels = [
        entry['week'].strftime('%d %b') for entry in weekly_qs
    ]
    weekly_counts = [entry['count'] for entry in weekly_qs]

    # ── Resolution rate per department ──────────────────────────────────
    dept_resolution = []
    for dept in Complaint.objects.values_list(
        'created_by__department', flat=True
    ).distinct():
        if not dept:
            continue
        dept_total    = Complaint.objects.filter(created_by__department=dept).count()
        dept_resolved = Complaint.objects.filter(
            created_by__department=dept, status='resolved'
        ).count()
        rate = round((dept_resolved / dept_total * 100), 1) if dept_total else 0
        dept_resolution.append({
            'dept':     dept,
            'total':    dept_total,
            'resolved': dept_resolved,
            'rate':     rate,
        })
    dept_resolution.sort(key=lambda x: x['rate'], reverse=True)

    # ── SLA tracking ────────────────────────────────────────────────────
    sla_data = _calculate_sla()

    # ── Overall stats ───────────────────────────────────────────────────
    total_all      = Complaint.objects.count()
    total_resolved = Complaint.objects.filter(status='resolved').count()
    overall_rate   = round(total_resolved / total_all * 100, 1) if total_all else 0
    escalated_count= Complaint.objects.filter(escalation_level__gt=1).count()

    return render(request, 'complaints/analytics.html', {
        'cat_labels':      json.dumps(list(cat_data.keys())),
        'cat_counts':      json.dumps(list(cat_data.values())),
        'dept_labels':     json.dumps(list(dept_data.keys())),
        'dept_counts':     json.dumps(list(dept_data.values())),
        'status_labels':   json.dumps(list(status_data.keys())),
        'status_counts':   json.dumps(list(status_data.values())),
        'weekly_labels':   json.dumps(weekly_labels),
        'weekly_counts':   json.dumps(weekly_counts),
        'dept_resolution': dept_resolution,
        'sla_data':        sla_data,
        'total_all':       total_all,
        'total_resolved':  total_resolved,
        'overall_rate':    overall_rate,
        'escalated_count': escalated_count,
        'range_filter':    days,
        'since':           since,
    })


# ─── Public Stats Page ────────────────────────────────────────────────────────

def public_stats_view(request):
    import datetime
    from django.utils import timezone

    total        = Complaint.objects.count()
    resolved     = Complaint.objects.filter(status='resolved').count()
    pending      = Complaint.objects.filter(status='pending').count()
    in_progress  = Complaint.objects.filter(status='in_progress').count()
    rate         = round(resolved / total * 100, 1) if total else 0

    # This month
    now          = timezone.now()
    month_start  = now.replace(day=1, hour=0, minute=0, second=0)
    this_month   = Complaint.objects.filter(created_at__gte=month_start).count()
    month_res    = Complaint.objects.filter(
        created_at__gte=month_start, status='resolved'
    ).count()

    # Top categories
    cat_counts = []
    for val, label in Complaint.Category.choices:
        count = Complaint.objects.filter(category=val).count()
        if count > 0:
            cat_counts.append({'label': label, 'count': count, 'val': val})
    cat_counts.sort(key=lambda x: x['count'], reverse=True)

    # Department performance (public — only shows dept name + rate)
    dept_perf = []
    for dept in Complaint.objects.values_list(
        'created_by__department', flat=True
    ).distinct():
        if not dept:
            continue
        t = Complaint.objects.filter(created_by__department=dept).count()
        r = Complaint.objects.filter(
            created_by__department=dept, status='resolved'
        ).count()
        if t >= 3:  # only show depts with enough data
            dept_perf.append({
                'dept':  dept,
                'total': t,
                'rate':  round(r / t * 100, 1),
            })
    dept_perf.sort(key=lambda x: x['rate'], reverse=True)

    return render(request, 'complaints/public_stats.html', {
        'total':       total,
        'resolved':    resolved,
        'pending':     pending,
        'in_progress': in_progress,
        'rate':        rate,
        'this_month':  this_month,
        'month_res':   month_res,
        'cat_counts':  cat_counts[:5],
        'dept_perf':   dept_perf,
    })


# ─── PDF Export ───────────────────────────────────────────────────────────────

@login_required
@user_passes_test(is_admin, login_url='complaints:feed')
def export_pdf_view(request):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph,
        Spacer, HRFlowable
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from io import BytesIO
    from django.http import HttpResponse
    import datetime

    # Filters from GET params
    status_filter   = request.GET.get('status', '')
    category_filter = request.GET.get('category', '')
    dept_filter     = request.GET.get('dept', '')
    date_from       = request.GET.get('date_from', '')
    date_to         = request.GET.get('date_to', '')

    complaints = Complaint.objects.select_related('created_by').order_by('-created_at')

    if status_filter:
        complaints = complaints.filter(status=status_filter)
    if category_filter:
        complaints = complaints.filter(category=category_filter)
    if dept_filter:
        complaints = complaints.filter(created_by__department__icontains=dept_filter)
    if date_from:
        try:
            complaints = complaints.filter(
                created_at__date__gte=datetime.date.fromisoformat(date_from)
            )
        except ValueError:
            pass
    if date_to:
        try:
            complaints = complaints.filter(
                created_at__date__lte=datetime.date.fromisoformat(date_to)
            )
        except ValueError:
            pass

    # Build PDF
    buffer = BytesIO()
    doc    = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20*mm, bottomMargin=20*mm,
        leftMargin=15*mm, rightMargin=15*mm
    )

    styles  = getSampleStyleSheet()
    story   = []

    # Title
    title_style = ParagraphStyle(
        'Title', parent=styles['Title'],
        fontSize=18, textColor=colors.HexColor('#1A3BC0'),
        spaceAfter=4
    )
    sub_style = ParagraphStyle(
        'Sub', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#5A5F7A'),
        spaceAfter=12
    )
    cell_style = ParagraphStyle(
        'Cell', parent=styles['Normal'],
        fontSize=7.5, leading=10
    )

    story.append(Paragraph("CampusVoice — Complaint Report", title_style))
    story.append(Paragraph(
        f"Generated: {datetime.datetime.now().strftime('%d %b %Y %H:%M')} | "
        f"Total records: {complaints.count()}",
        sub_style
    ))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=colors.HexColor('#1A3BC0')))
    story.append(Spacer(1, 8*mm))

    if not complaints.exists():
        story.append(Paragraph("No complaints found for the selected filters.", styles['Normal']))
    else:
        # Table header
        header = ['ID', 'Title', 'Category', 'Department', 'Status', 'Level', 'Date']
        data   = [header]

        for c in complaints:
            data.append([
                str(c.id),
                Paragraph(c.title[:60], cell_style),
                c.get_category_display(),
                c.created_by.department or '—',
                c.get_status_display(),
                f"L{c.escalation_level}",
                c.created_at.strftime('%d/%m/%Y'),
            ])

        col_widths = [12*mm, 55*mm, 28*mm, 35*mm, 25*mm, 12*mm, 22*mm]

        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A3BC0')),
            ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
            ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',   (0,0), (-1,0), 8),
            ('ALIGN',      (0,0), (-1,0), 'CENTER'),
            ('BOTTOMPADDING', (0,0), (-1,0), 6),
            ('TOPPADDING',    (0,0), (-1,0), 6),
            # Body
            ('FONTSIZE',   (0,1), (-1,-1), 7.5),
            ('ROWBACKGROUNDS', (0,1), (-1,-1),
             [colors.white, colors.HexColor('#F0F2F9')]),
            ('GRID',       (0,0), (-1,-1), 0.4, colors.HexColor('#D0D4E8')),
            ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,1), (-1,-1), 4),
            ('BOTTOMPADDING', (0,1), (-1,-1), 4),
            ('LEFTPADDING',   (0,0), (-1,-1), 4),
            ('RIGHTPADDING',  (0,0), (-1,-1), 4),
        ]))
        story.append(table)

    doc.build(story)
    buffer.seek(0)

    filename = f"campusvoice_report_{datetime.date.today()}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ─── HOD Weekly Digest ────────────────────────────────────────────────────────

def send_weekly_digest_view(request):
    """
    Trigger weekly digest manually or via a Monday visit.
    Only runs if not already sent this week.
    """
    from django.core.cache import cache
    from django.utils import timezone

    if cache.get('weekly_digest_sent'):
        return JsonResponse({'status': 'already_sent_this_week'})

    _send_weekly_digests()
    cache.set('weekly_digest_sent', True, timeout=6*24*3600)  # 6 days

    return JsonResponse({'status': 'sent'})


def _send_weekly_digests():
    """Send digest emails to all HODs."""
    from users.models import CustomUser, Role
    import datetime
    from django.utils import timezone

    hods       = CustomUser.objects.filter(role=Role.HOD, is_active=True)
    week_ago   = timezone.now() - datetime.timedelta(days=7)

    for hod in hods:
        dept = hod.department
        if not dept:
            continue

        week_complaints = Complaint.objects.filter(
            created_by__department=dept,
            created_at__gte=week_ago
        )
        total     = week_complaints.count()
        resolved  = week_complaints.filter(status='resolved').count()
        pending   = week_complaints.filter(status='pending').count()
        escalated = week_complaints.filter(escalation_level__gte=2).count()

        if total == 0:
            continue  # Don't send empty digests

        html = f"""
        <div style="font-family:sans-serif;max-width:520px;margin:0 auto;
             background:#fff;border-radius:16px;padding:32px;
             border:1px solid #e2e5f0;">
          <h2 style="color:#1A3BC0;margin-bottom:4px;">📊 Weekly Digest</h2>
          <p style="color:#888;font-size:13px;margin-top:0;">
            {dept} Department — Last 7 days
          </p>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:20px 0;">
            <div style="background:#f0f2f9;border-radius:8px;padding:16px;text-align:center;">
              <div style="font-size:28px;font-weight:700;color:#2a52e8;">{total}</div>
              <div style="font-size:12px;color:#888;">Total Complaints</div>
            </div>
            <div style="background:#dcfce7;border-radius:8px;padding:16px;text-align:center;">
              <div style="font-size:28px;font-weight:700;color:#16a34a;">{resolved}</div>
              <div style="font-size:12px;color:#888;">Resolved</div>
            </div>
            <div style="background:#fef3c7;border-radius:8px;padding:16px;text-align:center;">
              <div style="font-size:28px;font-weight:700;color:#d97706;">{pending}</div>
              <div style="font-size:12px;color:#888;">Still Pending</div>
            </div>
            <div style="background:#fee2e2;border-radius:8px;padding:16px;text-align:center;">
              <div style="font-size:28px;font-weight:700;color:#dc2626;">{escalated}</div>
              <div style="font-size:12px;color:#888;">Escalated to HOD+</div>
            </div>
          </div>
          <a href="https://campusvoice-bcw4.onrender.com/staff-dashboard/"
             style="display:block;background:#2a52e8;color:#fff;text-decoration:none;
                    text-align:center;padding:14px;border-radius:10px;
                    font-weight:700;margin-top:8px;">
            View Dashboard →
          </a>
          <p style="font-size:12px;color:#aaa;text-align:center;margin-top:16px;">
            CampusVoice — Automated Weekly Digest
          </p>
        </div>
        """

        try:
            import sib_api_v3_sdk
            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key['api-key'] = config('BREVO_API_KEY')
            api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
                sib_api_v3_sdk.ApiClient(configuration)
            )
            api_instance.send_transac_email(sib_api_v3_sdk.SendSmtpEmail(
                to=[{"email": hod.email, "name": hod.get_full_name()}],
                sender={"name": "CampusVoice", "email": "campusvoice.cms@gmail.com"},
                subject=f"[CampusVoice] Weekly Digest — {dept}",
                html_content=html,
            ))
        except Exception as e:
            print(f"Digest error for {hod.email}: {e}")


# ─── SLA Helper ───────────────────────────────────────────────────────────────

def _calculate_sla():
    """
    Returns list of dicts with avg resolution time per department.
    Only counts resolved complaints.
    """
    from django.utils import timezone

    sla_data = []
    depts = Complaint.objects.filter(
        status='resolved'
    ).values_list('created_by__department', flat=True).distinct()

    for dept in depts:
        if not dept:
            continue
        resolved = Complaint.objects.filter(
            created_by__department=dept,
            status='resolved'
        )
        if not resolved.exists():
            continue

        # Calculate avg hours to resolve
        total_hours = 0
        count       = 0
        for c in resolved:
            diff = (c.updated_at - c.created_at).total_seconds() / 3600
            total_hours += diff
            count += 1

        avg_hours = round(total_hours / count, 1) if count else 0

        if avg_hours <= 24:
            sla_status = 'good'
            sla_color  = '#16a34a'
            sla_label  = '✅ Good'
        elif avg_hours <= 48:
            sla_status = 'warning'
            sla_color  = '#d97706'
            sla_label  = '⚠️ Needs Improvement'
        else:
            sla_status = 'poor'
            sla_color  = '#dc2626'
            sla_label  = '❌ Poor'

        sla_data.append({
            'dept':      dept,
            'avg_hours': avg_hours,
            'count':     count,
            'status':    sla_status,
            'color':     sla_color,
            'label':     sla_label,
        })

    sla_data.sort(key=lambda x: x['avg_hours'])
    return sla_data
# ─── Email Helpers ────────────────────────────────────────────────────────────

def _brevo_send(to_email, to_name, subject, html_content):
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = config('BREVO_API_KEY')
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )
    email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": to_email, "name": to_name}],
        sender={"name": "CampusVoice", "email": "campusvoice.cms@gmail.com"},
        subject=subject,
        html_content=html_content,
    )
    try:
        api_instance.send_transac_email(email)
    except ApiException as e:
        print(f"Brevo error: {e}")
        raise


def _notify_status_change(complaint):
    html = render_to_string('emails/status_update.html', {
        'complaint':    complaint,
        'student_name': complaint.created_by.first_name,
    })
    _brevo_send(
        complaint.created_by.email,
        complaint.created_by.get_full_name(),
        f"[CampusVoice] Complaint status: {complaint.get_status_display()}",
        html
    )


def _notify_escalation(complaint):
    from users.models import CustomUser, Role
    if complaint.escalation_level == 2:
        recipients  = CustomUser.objects.filter(
            role=Role.HOD,
            department=complaint.created_by.department,
            is_active=True
        )
        level_label = "HOD"
    elif complaint.escalation_level == 3:
        recipients  = CustomUser.objects.filter(role=Role.AUTHORITY, is_active=True)
        level_label = "Higher Authority"
    else:
        return

    if not recipients.exists():
        return

    html = render_to_string('emails/escalation_notify.html', {
        'complaint':   complaint,
        'level_label': level_label,
    })
    for r in recipients:
        try:
            _brevo_send(r.email, r.get_full_name(),
                f"[CampusVoice] ⚠️ Escalated to {level_label}: {complaint.title[:50]}", html)
        except Exception as e:
            print(f"Escalation notify error for {r.email}: {e}")


def _notify_student_update(complaint, content):
    from users.models import CustomUser, Role
    # Notify the dept user / staff handling this complaint
    recipients = CustomUser.objects.filter(
        role=Role.DEPT_USER,
        department=complaint.created_by.department,
        is_active=True
    )
    if not recipients.exists():
        return
    html = render_to_string('emails/student_update_notify.html', {
        'complaint': complaint,
        'content':   content,
    })
    for r in recipients:
        try:
            _brevo_send(r.email, r.get_full_name(),
                f"[CampusVoice] Student added update on complaint #{complaint.id}", html)
        except Exception as e:
            print(f"Student update notify error: {e}")


def _notify_staff_question(complaint, message_text, staff_user):
    student = complaint.created_by
    html    = render_to_string('emails/staff_question_notify.html', {
        'complaint':    complaint,
        'message_text': message_text,
        'staff_name':   staff_user.get_full_name(),
    })
    _brevo_send(
        student.email,
        student.get_full_name(),
        f"[CampusVoice] Staff has a question about your complaint #{complaint.id}",
        html
    )