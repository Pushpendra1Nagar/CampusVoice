from django.contrib import admin
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Complaint
from .views import _notify_status_change


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'status', 'created_by', 'created_at')
    list_filter = ('status', 'category')
    search_fields = ('title', 'description', 'created_by__email')
    readonly_fields = ('created_by', 'created_at', 'updated_at')
    fieldsets = (
        ('Complaint Info', {'fields': ('title', 'category', 'description', 'image')}),
        ('Status', {'fields': ('status', 'admin_remark')}),
        ('Meta', {'fields': ('created_by', 'created_at', 'updated_at')}),
    )

    def save_model(self, request, obj, form, change):
        if change and 'status' in form.changed_data:
            super().save_model(request, obj, form, change)
            _notify_status_change(obj)  # Email student on status change
        else:
            super().save_model(request, obj, form, change)
