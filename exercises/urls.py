from django.urls import path
from . import views

app_name = 'exercises'

urlpatterns = [
    # Exercise urls
    path('', views.exercise_list, name='exercise_list'),
    path('<int:pk>/', views.exercise_detail, name='exercise_detail'),
    path('<int:exercise_id>/guidance/', views.get_guidance, name='get_guidance'),
    path('<int:exercise_id>/<str:filename>', views.serve_asset, name='serve_asset'),

    # Course urls
    path('courses/', views.course_list, name='course_list'),
    path('courses/<int:pk>/', views.course_detail, name='course_detail'),
] 