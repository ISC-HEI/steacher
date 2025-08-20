from django.urls import path
from . import views

app_name = 'exercises'

urlpatterns = [

    # Course urls
    path('courses/', views.course_list, name='course_list'),
    path('courses/<int:pk>/', views.course_detail, name='course_detail'),

    # Exercise urls
    path('', views.exercise_list, name='exercise_list'),
    path('<int:pk>/', views.exercise_detail, name='exercise_detail'),
    path('<int:exercise_id>/traces/<int:trace_id>/guidance/', views.get_guidance, name='get_guidance'),
    path('<int:exercise_id>/<str:filename>', views.serve_asset, name='serve_asset'),
    path('<int:exercise_id>/delete_answers/', views.delete_user_answers, name='delete_user_answers'),

    # Teacher URLs for exercise management
    path('courses/<int:course_pk>/add_exercise/', views.exercise_form, name='exercise_add'),
    path('courses/<int:course_pk>/edit_exercise/<int:exercise_pk>/', views.exercise_form, name='exercise_edit'),
] 