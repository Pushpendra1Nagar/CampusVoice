# from django.shortcuts import render, redirect, get_object_or_404
# from django.contrib.auth.decorators import login_required
# from django.contrib import messages
# from django.http import JsonResponse
# from django.template.loader import render_to_string
# from django.conf import settings
# from django.db.models import Count, Q
# from decouple import config

# from .models import Complaint, ComplaintUpvote
# from .forms import ComplaintForm


# def feed_view(request):
#     """Public anonymous feed — anyone can view, author hidden."""
#     complaints = Complaint.objects.annotate(
#         upvote_count=Count('upvotes')
#     ).select_related('created_by')

#     # Filters
#     category = request.GET.get('category', '')
#     status = request.GET.get('status', '')
#     search = request.GET.get('q', '')

#     if category:
#         complaints = complaints.filter(category=category)
#     if status:
#         complaints = complaints.filter(status=status)
#     if search:
#         complaints = complaints.filter(
#             Q(title__icontains=search) | Q(description__icontains=search)
#         )

#     # Which complaints has the logged-in user upvoted?
#     user_upvoted_ids = set()
#     if request.user.is_authenticated:
#         user_upvoted_ids = set(
#             ComplaintUpvote.objects.filter(user=request.user)
#             .values_list('complaint_id', flat=True)
#         )

#     return render(request, 'complaints/feed.html', {
#         'complaints': complaints,
#         'user_upvoted_ids': user_upvoted_ids,
#         'categories': Complaint.Category.choices,
#         'statuses': Complaint.Status.choices,
#         'active_category': category,
#         'active_status': status,
#         'search_query': search,
#     })


# @login_required
# def submit_complaint_view(request):
#     form = ComplaintForm(request.POST or None, request.FILES or None)
#     if request.method == 'POST' and form.is_valid():
#         complaint = form.save(commit=False)
#         complaint.created_by = request.user
#         complaint.save()
#         messages.success(request, "Your complaint has been submitted anonymously!")
#         return redirect('complaints:feed')

#     return render(request, 'complaints/submit.html', {'form': form})


# def complaint_detail_view(request, pk):
#     complaint = get_object_or_404(Complaint, pk=pk)
#     is_owner = request.user.is_authenticated and complaint.created_by == request.user
#     upvote_count = complaint.upvotes.count()
#     user_upvoted = (
#         request.user.is_authenticated and
#         ComplaintUpvote.objects.filter(complaint=complaint, user=request.user).exists()
#     )

#     return render(request, 'complaints/detail.html', {
#         'complaint': complaint,
#         'is_owner': is_owner,
#         'upvote_count': upvote_count,
#         'user_upvoted': user_upvoted,
#     })


# @login_required
# def upvote_view(request, pk):
#     """Toggle upvote — returns JSON for AJAX calls."""
#     if request.method != 'POST':
#         return JsonResponse({'error': 'Method not allowed'}, status=405)

#     complaint = get_object_or_404(Complaint, pk=pk)
#     upvote, created = ComplaintUpvote.objects.get_or_create(
#         complaint=complaint, user=request.user
#     )
#     if not created:
#         upvote.delete()
#         upvoted = False
#     else:
#         upvoted = True

#     return JsonResponse({
#         'upvoted': upvoted,
#         'count': complaint.upvotes.count(),
#     })


# @login_required
# def my_complaints_view(request):
#     """Logged-in user sees their own complaints with author info."""
#     complaints = request.user.complaints.annotate(
#         upvote_count=Count('upvotes')
#     ).order_by('-created_at')
#     return render(request, 'complaints/my_complaints.html', {
#         'complaints': complaints
#     })


# # ─── Admin webhook: send email when status changes ───────────────────────────

# def _notify_status_change(complaint):
#     import sib_api_v3_sdk
#     from sib_api_v3_sdk.rest import ApiException

#     configuration = sib_api_v3_sdk.Configuration()
#     configuration.api_key['api-key'] = config('BREVO_API_KEY')

#     api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
#         sib_api_v3_sdk.ApiClient(configuration)
#     )

#     html_content = render_to_string('emails/status_update.html', {
#         'complaint': complaint,
#         'student_name': complaint.created_by.first_name,
#     })

#     send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
#         to=[{"email": complaint.created_by.email}],
#         sender={"name": "CampusVoice", "email": "campusvoice.cms@gmail.com"},
#         subject=f"[CampusVoice] Complaint status updated: {complaint.get_status_display()}",
#         html_content=html_content,
#     )

#     try:
#         api_instance.send_transac_email(send_smtp_email)
#     except ApiException as e:
#         print(f"Brevo API error: {e}")


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
