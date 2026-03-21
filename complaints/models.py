from django.db import models
from django.conf import settings
from cloudinary.models import CloudinaryField


class Complaint(models.Model):
    """Core complaint model for CampusVoice."""

    class Category(models.TextChoices):
        HOSTEL = 'hostel', 'Hostel'
        ACADEMICS = 'academics', 'Academics'
        INFRASTRUCTURE = 'infrastructure', 'Infrastructure'
        LIBRARY = 'library', 'Library'
        CANTEEN = 'canteen', 'Canteen'
        SPORTS = 'sports', 'Sports & Facilities'
        HARASSMENT = 'harassment', 'Harassment'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        RESOLVED = 'resolved', 'Resolved'
        REJECTED = 'rejected', 'Rejected'

    # Core fields
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.OTHER
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    # Media proof (stored on Cloudinary)
    image = CloudinaryField('image', blank=True, null=True)

    # Relations — FK hidden from public feed
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='complaints',
    )

    # Admin notes
    admin_remark = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Complaint'

    def __str__(self):
        return f"[{self.get_category_display()}] {self.title}"

    @property
    def status_badge_class(self):
        """CSS class for status badge."""
        return {
            'pending': 'badge-warning',
            'in_progress': 'badge-info',
            'resolved': 'badge-success',
            'rejected': 'badge-danger',
        }.get(self.status, 'badge-secondary')

    @property
    def category_icon(self):
        """Emoji icon per category."""
        return {
            'hostel': '🏠', 'academics': '📚', 'infrastructure': '🏗️',
            'library': '📖', 'canteen': '🍽️', 'sports': '⚽',
            'harassment': '🚨', 'other': '📋',
        }.get(self.category, '📋')


class ComplaintUpvote(models.Model):
    """Track which users upvoted which complaints."""
    complaint = models.ForeignKey(
        Complaint, on_delete=models.CASCADE, related_name='upvotes'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('complaint', 'user')
