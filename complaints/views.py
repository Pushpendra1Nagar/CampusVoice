from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import Count, Q
from decouple import config

from .models import Complaint, ComplaintUpvote
from .forms import ComplaintForm


def feed_view(request):
    """Public anonymous feed — anyone can view, author hidden."""
    complaints = Complaint.objects.annotate(
        upvote_count=Count('upvotes')
    ).select_related('created_by')

    # Filters
    category = request.GET.get('category', '')
    status = request.GET.get('status', '')
    search = request.GET.get('q', '')

    if category:
        complaints = complaints.filter(category=category)
    if status:
        complaints = complaints.filter(status=status)
    if search:
        complaints = complaints.filter(
            Q(title__icontains=search) | Q(description__icontains=search)
        )

    # Which complaints has the logged-in user upvoted?
    user_upvoted_ids = set()
    if request.user.is_authenticated:
        user_upvoted_ids = set(
            ComplaintUpvote.objects.filter(user=request.user)
            .values_list('complaint_id', flat=True)
        )

    return render(request, 'complaints/feed.html', {
        'complaints': complaints,
        'user_upvoted_ids': user_upvoted_ids,
        'categories': Complaint.Category.choices,
        'statuses': Complaint.Status.choices,
        'active_category': category,
        'active_status': status,
        'search_query': search,
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
    upvote_count = complaint.upvotes.count()
    user_upvoted = (
        request.user.is_authenticated and
        ComplaintUpvote.objects.filter(complaint=complaint, user=request.user).exists()
    )

    return render(request, 'complaints/detail.html', {
        'complaint': complaint,
        'is_owner': is_owner,
        'upvote_count': upvote_count,
        'user_upvoted': user_upvoted,
    })


@login_required
def upvote_view(request, pk):
    """Toggle upvote — returns JSON for AJAX calls."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    complaint = get_object_or_404(Complaint, pk=pk)
    upvote, created = ComplaintUpvote.objects.get_or_create(
        complaint=complaint, user=request.user
    )
    if not created:
        upvote.delete()
        upvoted = False
    else:
        upvoted = True

    return JsonResponse({
        'upvoted': upvoted,
        'count': complaint.upvotes.count(),
    })


@login_required
def my_complaints_view(request):
    """Logged-in user sees their own complaints with author info."""
    complaints = request.user.complaints.annotate(
        upvote_count=Count('upvotes')
    ).order_by('-created_at')
    return render(request, 'complaints/my_complaints.html', {
        'complaints': complaints
    })


# ─── Admin webhook: send email when status changes ───────────────────────────

def _notify_status_change(complaint):
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException

    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = config('BREVO_API_KEY')

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    html_content = render_to_string('emails/status_update.html', {
        'complaint': complaint,
        'student_name': complaint.created_by.first_name,
    })

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": complaint.created_by.email}],
        sender={"name": "CampusVoice", "email": "campusvoice.cms@gmail.com"},
        subject=f"[CampusVoice] Complaint status updated: {complaint.get_status_display()}",
        html_content=html_content,
    )

    try:
        api_instance.send_transac_email(send_smtp_email)
    except ApiException as e:
        print(f"Brevo API error: {e}")
    """Called by admin signal when complaint status is updated."""
    student_email = complaint.created_by.email
    subject = f"[CampusVoice] Your complaint status: {complaint.get_status_display()}"
    html_message = render_to_string('emails/status_update.html', {
        'complaint': complaint,
        'student_name': complaint.created_by.first_name,
    })
    send_mail(
        subject=subject,
        message=f"Your complaint '{complaint.title}' is now {complaint.get_status_display()}.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[student_email],
        html_message=html_message,
        fail_silently=True,
    )
