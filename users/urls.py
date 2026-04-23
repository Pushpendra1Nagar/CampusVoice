from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # Auth
    path('register/',           views.register_view,              name='register'),
    path('verify/',             views.verify_otp_view,            name='verify_otp'),
    path('resend-otp/',         views.resend_otp_view,            name='resend_otp'),
    path('login/',              views.login_view,                  name='login'),
    path('logout/',             views.logout_view,                 name='logout'),

    # Profile
    path('profile/',            views.profile_view,               name='profile'),
    path('change-password/',    views.change_password_view,       name='change_password'),

    # Password Reset
    path('password-reset/',         views.password_reset_request_view, name='password_reset'),
    path('password-reset/verify/',  views.password_reset_verify_view,  name='password_reset_verify'),

    # Admin — Staff Management
    path('create-staff/',           views.create_staff_view,       name='create_staff'),
    path('manage-staff/',           views.manage_staff_view,       name='manage_staff'),
    path('manage-staff/<int:pk>/deactivate/', views.deactivate_staff_view, name='deactivate_staff'),
    path('manage-staff/<int:pk>/delete/',     views.delete_staff_view,     name='delete_staff'),
]