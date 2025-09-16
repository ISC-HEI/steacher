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
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from exercises.views_students import dashboard
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
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
    path('exercises/', include((exercises_urls.students_urlpatterns, 'exercises'), namespace='exercises')),
    path('teachers/', include((exercises_urls.teachers_urlpatterns, 'teachers'), namespace='teachers')),
    path('', login_required(dashboard), name='dashboard_root'),  # Root shows student dashboard (requires login)
]

# Serve static files during development FIXME make serving static files work in production
if settings.DEBUG:
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns
    urlpatterns += staticfiles_urlpatterns()
