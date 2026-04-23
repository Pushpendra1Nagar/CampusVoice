import re
from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser


class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=50, required=True)
    last_name = forms.CharField(max_length=50, required=True)
    email = forms.EmailField(required=True)
    roll_number = forms.CharField(max_length=12, required=True, label='Enrollment Number')
    department = forms.CharField(max_length=100, required=True)
    year_of_study = forms.IntegerField(required=True, min_value=1, max_value=4)
    degree = forms.CharField(max_length=20, required=True)

    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'email', 'username',
                  'roll_number', 'department', 'year_of_study', 'degree',
                  'password1', 'password2')

    def clean_roll_number(self):
        enrollment = self.cleaned_data.get('roll_number', '').upper()
        pattern = r'^[A-Z]{2}[0-9]{10}$'
        if not re.match(pattern, enrollment):
            raise forms.ValidationError(
                'Invalid enrollment number. Must be 2 capital letters + 10 digits (e.g. AZ2060999062)'
            )
        if CustomUser.objects.filter(roll_number=enrollment).exists():
            raise forms.ValidationError('This enrollment number is already registered.')
        return enrollment

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower()
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError('This email is already registered.')
        return email


class OTPVerifyForm(forms.Form):
    otp = forms.CharField(max_length=6, min_length=6)


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'department', 'year_of_study', 'degree', 'profile_picture')