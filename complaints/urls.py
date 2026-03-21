from django.urls import path
from . import views

app_name = 'complaints'

urlpatterns = [
    path('', views.feed_view, name='feed'),
    path('submit/', views.submit_complaint_view, name='submit'),
    path('mine/', views.my_complaints_view, name='my_complaints'),
    path('<int:pk>/', views.complaint_detail_view, name='detail'),
    path('<int:pk>/upvote/', views.upvote_view, name='upvote'),
]
