from django.db import models
from django.conf import settings
from django.utils import timezone
from cloudinary.models import CloudinaryField


class Complaint(models.Model):

    class Category(models.TextChoices):
        HOSTEL = 'hostel', 'Hostel'
        ACADEMICS = 'academics', 'Academics'
        INFRASTRUCTURE = 'infrastructure', 'Infrastructure'
        LIBRARY = 'library', 'Library'
        CANTEEN = 'canteen', 'Canteen'
        SPORTS = 'sports', 'Sports & Facilities'
        HARASSMENT = 'harassment', 'Ragging'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        RESOLVED = 'resolved', 'Resolved'
        REJECTED = 'rejected', 'Rejected'
        WITHDRAWN  = 'withdrawn',  'Withdrawn'

    class EscalationLevel(models.IntegerChoices):
        LEVEL_1 = 1, 'Level 1 — Department User'
        LEVEL_2 = 2, 'Level 2 — HOD'
        LEVEL_3 = 3, 'Level 3 — Higher Authority'

    # Core fields
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    image = CloudinaryField('image', blank=True, null=True)

    # Escalation
    escalation_level = models.IntegerField(choices=EscalationLevel.choices, default=1)
    escalated_at = models.DateTimeField(null=True, blank=True)  # when it moved to current level
    last_escalation_check = models.DateTimeField(auto_now_add=True)

    # Relations
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='complaints'
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_complaints'
    )

    # Admin notes
    admin_remark = models.TextField(blank=True)
    escalation_note = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[L{self.escalation_level}] {self.title}"

    @property
    def status_badge_class(self):
        return {
            'pending': 'badge-warning',
            'in_progress': 'badge-info',
            'resolved': 'badge-success',
            'rejected': 'badge-danger',
        }.get(self.status, 'badge-secondary')

    @property
    def category_icon(self):
        return {
            'hostel': '🏠', 'academics': '📚', 'infrastructure': '🏗️',
            'library': '📖', 'canteen': '🍽️', 'sports': '⚽',
            'harassment': '🚨', 'other': '📋',
        }.get(self.category, '📋')

    @property
    def escalation_level_label(self):
        return {
            1: '👤 Dept. User',
            2: '🎓 HOD',
            3: '🏛️ Higher Authority',
        }.get(self.escalation_level, 'Unknown')

    @property
    def escalation_badge_class(self):
        return {1: 'badge-info', 2: 'badge-warning', 3: 'badge-danger'}.get(self.escalation_level, '')

    def hours_at_current_level(self):
        ref = self.escalated_at or self.created_at
        return (timezone.now() - ref).total_seconds() / 3600

    def should_escalate(self):
        """Level 1 → 2 after 24hrs. Level 2 → 3 after 48hrs total (24 more)."""
        if self.status in ['resolved', 'rejected']:
            return False
        hours = self.hours_at_current_level()
        if self.escalation_level == 1 and hours >= 24:
            return True
        if self.escalation_level == 2 and hours >= 24:
            return True
        return False

    def escalate(self):
        if self.escalation_level < 3:
            self.escalation_level += 1
            self.escalated_at = timezone.now()
            self.escalation_note += f"\nEscalated to Level {self.escalation_level} on {timezone.now().strftime('%d %b %Y %H:%M')}"
            self.save()
            return True
        return False
# complaints/models.py — add inside Complaint class

    @property
    def has_unread_staff_messages(self):
        """Unread staff messages for student to see."""
        return self.messages.filter(
            sender_type='staff',
            is_read=False
        ).exists()

    @property
    def has_unread_student_messages(self):
        """Unread student messages for staff to see."""
        return self.messages.filter(
            sender_type='student',
            is_read=False
        ).exists()

    @property
    def unread_staff_message_count(self):
        """Count of unread staff messages."""
        return self.messages.filter(
            sender_type='staff',
            is_read=False
        ).count()

    @property
    def unread_student_message_count(self):
        """Count of unread student messages."""
        return self.messages.filter(
            sender_type='student',
            is_read=False
        ).count()

    @property
    def message_count(self):
        """Total message count."""
        return self.messages.count()

    @property
    def is_active(self):
        """Whether complaint is still open."""
        return self.status not in ['resolved', 'rejected', 'withdrawn']

class ComplaintUpvote(models.Model):
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='upvotes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('complaint', 'user')

class ComplaintUpdate(models.Model):
    """Student can add follow-up information to their complaint."""
    complaint  = models.ForeignKey(
        Complaint, on_delete=models.CASCADE, related_name='updates'
    )
    added_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    content    = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Update on #{self.complaint.id} by {self.added_by.email}"


class ComplaintMessage(models.Model):
    """Staff can ask questions, student can reply — private thread per complaint."""

    class SenderType(models.TextChoices):
        STAFF   = 'staff',   'Staff'
        STUDENT = 'student', 'Student'

    complaint   = models.ForeignKey(
        Complaint, on_delete=models.CASCADE, related_name='messages'
    )
    sender      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    sender_type = models.CharField(
        max_length=10, choices=SenderType.choices
    )
    message     = models.TextField()
    is_read     = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.sender_type}] on #{self.complaint.id}"

class Notification(models.Model):
    """In-app notifications for students and staff."""

    class NotifType(models.TextChoices):
        STATUS_CHANGE  = 'status_change',  'Status Changed'
        ESCALATED      = 'escalated',      'Complaint Escalated'
        STAFF_MESSAGE  = 'staff_message',  'Message from Staff'
        STUDENT_UPDATE = 'student_update', 'Student Added Update'
        RESOLVED       = 'resolved',       'Complaint Resolved'

    user        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    complaint   = models.ForeignKey(
        Complaint, on_delete=models.CASCADE,
        null=True, blank=True
    )
    notif_type  = models.CharField(max_length=20, choices=NotifType.choices)
    title       = models.CharField(max_length=200)
    message     = models.TextField()
    is_read     = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.notif_type}] {self.user.email} — {self.title}"


class AuditLog(models.Model):
    """Permanent audit trail of all admin/staff actions."""

    class ActionType(models.TextChoices):
        STATUS_CHANGE    = 'status_change',    'Status Changed'
        ACCOUNT_CREATED  = 'account_created',  'Account Created'
        ACCOUNT_DELETED  = 'account_deleted',  'Account Deleted'
        ACCOUNT_DEACTIVATED = 'account_deactivated', 'Account Deactivated'
        ACCOUNT_REACTIVATED = 'account_reactivated', 'Account Reactivated'
        BULK_UPDATE      = 'bulk_update',      'Bulk Update'
        COMPLAINT_DELETED= 'complaint_deleted','Complaint Deleted'
        LOGIN            = 'login',            'User Login'

    performed_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, related_name='audit_logs'
    )
    action_type   = models.CharField(max_length=30, choices=ActionType.choices)
    target_model  = models.CharField(max_length=50, blank=True)
    target_id     = models.PositiveIntegerField(null=True, blank=True)
    description   = models.TextField()
    ip_address    = models.GenericIPAddressField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.action_type}] by {self.performed_by} at {self.created_at}"

    @classmethod
    def log(cls, performed_by, action_type, description,
            target_model='', target_id=None, request=None):
        ip = None
        if request:
            x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')
        cls.objects.create(
            performed_by=performed_by,
            action_type=action_type,
            description=description,
            target_model=target_model,
            target_id=target_id,
            ip_address=ip,
        )