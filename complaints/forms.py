from django import forms
from .models import Complaint


class ComplaintForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = ('title', 'category', 'description', 'image')
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Brief title of your complaint'}),
            'description': forms.Textarea(attrs={'placeholder': 'Describe your issue in detail...', 'rows': 6}),
        }


class AdminRemarkForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = ('status', 'admin_remark')
        widgets = {
            'admin_remark': forms.Textarea(attrs={
                'placeholder': 'Add a remark for the student (optional)...',
                'rows': 4
            }),
        }
        labels = {
            'status': 'Update Status',
            'admin_remark': 'Admin Remark (visible to student)',
        }
