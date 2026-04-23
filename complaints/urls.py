from django.urls import path
from . import views

app_name = 'complaints'

urlpatterns = [
    # Public
    path('',                         views.feed_view,                   name='feed'),
    path('track/',                   views.complaint_tracker_view,      name='track'),
    path('<int:pk>/',                views.complaint_detail_view,       name='detail'),
    path('<int:pk>/upvote/',         views.upvote_view,                 name='upvote'),

    # Student
    path('submit/',                  views.submit_complaint_view,       name='submit'),
    path('submit/success/<int:pk>/', views.submit_success_view,         name='submit_success'),
    path('mine/',                    views.my_complaints_view,          name='my_complaints'),
    path('dashboard/',               views.student_dashboard_view,      name='student_dashboard'),
    path('<int:pk>/edit/',           views.edit_complaint_view,         name='edit'),
    path('<int:pk>/delete/',         views.delete_complaint_view,       name='delete'),
    path('<int:pk>/withdraw/',       views.withdraw_complaint_view,     name='withdraw'),
    path('<int:pk>/add-update/',     views.add_update_view,             name='add_update'),
    path('<int:pk>/reply/',          views.student_reply_view,          name='student_reply'),

    # Staff
    path('staff-dashboard/',         views.staff_dashboard_view,        name='staff_dashboard'),
    path('staff-update/<int:pk>/',   views.staff_update_complaint_view, name='staff_update'),
    path('staff-ask/<int:pk>/',      views.staff_ask_view,              name='staff_ask'),

    # Admin
    path('admin-panel/',             views.admin_dashboard_view,        name='admin_dashboard'),
    path('admin-panel/<int:pk>/update/', views.admin_update_complaint_view, name='admin_update'),

    # Escalation
    path('check-escalations/',       views.trigger_escalation_view,    name='trigger_escalation'),
    
    # Analytics & Reports
    path('analytics/',         views.analytics_view,          name='analytics'),
    path('stats/',             views.public_stats_view,        name='public_stats'),
    path('export/pdf/',        views.export_pdf_view,          name='export_pdf'),
    path('weekly-digest/',     views.send_weekly_digest_view,  name='weekly_digest'),
]