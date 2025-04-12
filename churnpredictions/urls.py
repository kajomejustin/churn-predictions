from django.contrib import admin
from django.urls import path
from dashboard import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.dashboard, name='dashboard'),
    path('dashboard-data/', views.dashboard_data, name='dashboard_data'),
    path('get_predictions/', views.get_predictions, name='get_predictions'),
]

from django.conf import settings
from django.conf.urls.static import static

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)