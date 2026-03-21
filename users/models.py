from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import random


class CustomUser(AbstractUser):
    """Extended user model for CampusVoice students."""
    email = models.EmailField(unique=True)
    roll_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True)
    year_of_study = models.PositiveSmallIntegerField(null=True, blank=True)
    profile_picture = models.ImageField(
        upload_to='profile_pics/', null=True, blank=True
    )
    is_email_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        verbose_name = 'Student'
        verbose_name_plural = 'Students'

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    @property
    def display_name(self):
        """Anonymous display name for public feed."""
        return f"Student#{self.id:04d}"


class OTPCode(models.Model):
    """One-time password for email verification."""
    email = models.EmailField()
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'OTP Code'

    def __str__(self):
        return f"OTP for {self.email} — {self.code}"

    @classmethod
    def generate(cls, email):
        """Generate a fresh 6-digit OTP and invalidate old ones."""
        cls.objects.filter(email=email, is_used=False).update(is_used=True)
        code = str(random.randint(100000, 999999))
        return cls.objects.create(email=email, code=code)

    def is_valid(self):
        """Check if OTP is within 10-minute window and unused."""
        from django.conf import settings
        expiry_minutes = getattr(settings, 'OTP_EXPIRY_MINUTES', 10)
        age = (timezone.now() - self.created_at).total_seconds() / 60
        return not self.is_used and age <= expiry_minutes
