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


class ComplaintUpvote(models.Model):
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='upvotes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('complaint', 'user')