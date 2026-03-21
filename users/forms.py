from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser


class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=50, required=True)
    last_name = forms.CharField(max_length=50, required=True)
    email = forms.EmailField(required=True)
    roll_number = forms.CharField(max_length=20, required=False)
    department = forms.CharField(max_length=100, required=False)

    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'email', 'username',
                  'roll_number', 'department', 'password1', 'password2')


class OTPVerifyForm(forms.Form):
    otp = forms.CharField(
        max_length=6, min_length=6,
        widget=forms.TextInput(attrs={
            'placeholder': '6-digit code', 'autocomplete': 'one-time-code',
            'inputmode': 'numeric', 'maxlength': '6', 'class': 'otp-input'
        })
    )


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'department', 'year_of_study', 'profile_picture')
