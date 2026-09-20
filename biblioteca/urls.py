from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/', include('chamados.api_urls')),
    path('', include('chamados.urls')),
]
