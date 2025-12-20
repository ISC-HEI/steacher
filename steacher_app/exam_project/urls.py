"""
URL configuration for exam_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from exercises import urls as exercises_urls
from exercises.views_students import register
from exercises.views_mobile import mobile_magic_login
from django.conf import settings
from django.conf.urls.static import static
from .views import home

urlpatterns = [
    path('admin/', admin.site.urls),
    # Mobile magic link (short URL at root level)
    path('reg/<str:token>', mobile_magic_login, name='mobile_magic_login'),
    path('accounts/register/', register, name='register'),
    # Override password reset confirm to redirect to home/dashboard after success
    path(
        'accounts/reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(success_url=reverse_lazy('dashboard_root')),
        name='password_reset_confirm',
    ),
    # Override password change success to redirect to home/dashboard
    path(
        'accounts/password_change/',
        auth_views.PasswordChangeView.as_view(success_url=reverse_lazy('dashboard_root')),
        name='password_change',
    ),
    path('accounts/', include('django.contrib.auth.urls')),
    path('m/', include((exercises_urls.mobile_urlpatterns, 'mobile'), namespace='mobile')),
    path('exercises/', include((exercises_urls.urlpatterns, 'exercises'), namespace='exercises')),
    path('teachers/', include((exercises_urls.teachers_urlpatterns, 'teachers'), namespace='teachers')),
    path('teacher/authoring-assistant/', include('authoring_tools.urls')),
    path('evaluation/', include('evaluation.urls')),
    path('', home, name='dashboard_root'),  # Root auto-detects mobile and redirects accordingly
]

# Serve static files during development FIXME make serving static files work in production
if settings.DEBUG:
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns
    urlpatterns += staticfiles_urlpatterns()
