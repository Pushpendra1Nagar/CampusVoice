from django import forms
from .models import Complaint


class ComplaintForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = ('title', 'category', 'description', 'image')
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Brief title of your complaint'}),
            'description': forms.Textarea(attrs={
                'placeholder': 'Describe your issue in detail...',
                'rows': 6
            }),
        }
