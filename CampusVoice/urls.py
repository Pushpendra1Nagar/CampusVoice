from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from complaints import views as cv

urlpatterns = [
    path('admin/',   admin.site.urls),
    path('home/',    cv.landing_view,  name='landing'),
    path('',         include('complaints.urls', namespace='complaints')),
    path('auth/',    include('users.urls',       namespace='users')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)