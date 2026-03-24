from django.urls import path
from . import views

app_name = 'complaints'

urlpatterns = [
    path('', views.feed_view, name='feed'),
    path('submit/', views.submit_complaint_view, name='submit'),
    path('mine/', views.my_complaints_view, name='my_complaints'),
    path('<int:pk>/', views.complaint_detail_view, name='detail'),
    path('<int:pk>/upvote/', views.upvote_view, name='upvote'),
    path('<int:pk>/edit/', views.edit_complaint_view, name='edit'),
    path('<int:pk>/delete/', views.delete_complaint_view, name='delete'),
    # Admin routes
    path('admin-panel/', views.admin_dashboard_view, name='admin_dashboard'),
    path('admin-panel/<int:pk>/update/', views.admin_update_complaint_view, name='admin_update'),
    path('check-escalations/', views.trigger_escalation_view, name='trigger_escalation'),
    path('staff-dashboard/', views.staff_dashboard_view, name='staff_dashboard'),
    path('staff-update/<int:pk>/', views.staff_update_complaint_view, name='staff_update'),
]
