from django.urls import path
from . import views_students, views_teachers

app_name = 'exercises'

# Students' URL patterns
students_urlpatterns = [
    path('dashboard/', views_students.dashboard, name='dashboard'),
    path('chat/', views_students.chat_home, name='chat_home'),
    path('chat/threads/', views_students.chat_threads, name='chat_threads'),
    path('chat/threads/<int:thread_id>/', views_students.chat_thread_detail, name='chat_thread_detail'),
    path('chat/threads/<int:thread_id>/send/', views_students.chat_thread_send, name='chat_thread_send'),
    path('chat/threads/<int:thread_id>/delete/', views_students.chat_thread_delete, name='chat_thread_delete'),
    path('courses/', views_students.course_list, name='course_list'),
    path('courses/<int:pk>/', views_students.course_detail, name='course_detail'),
    path('', views_students.exercise_list, name='exercise_list'),
    # More specific patterns first to avoid conflicts
    path('<int:exercise_id>/attempts/<int:attempt_id>/guidance/', views_students.get_guidance, name='get_guidance'),
    path('<int:exercise_id>/delete_answers/', views_students.delete_user_answers, name='delete_user_answers'),
    path('<int:exercise_id>/<str:filename>', views_students.serve_asset, name='serve_asset'),
    # Generic pattern last
    path('<int:pk>/', views_students.exercise_detail, name='exercise_detail'),
]

# Teachers' URL patterns (namespaced at project level under 'teachers')
teachers_urlpatterns = [
    path('courses/', views_teachers.course_list, name='course_list'),
    path('courses/<int:pk>/', views_teachers.course_detail, name='course_detail'),
    path('courses/<int:course_pk>/add_exercise/', views_teachers.exercise_form, name='exercise_add'),
    path('courses/<int:course_pk>/edit_exercise/<int:exercise_pk>/', views_teachers.exercise_form, name='exercise_edit'),

    path('api/reorder_modules/', views_teachers.reorder_modules, name='reorder_modules'),
    path('api/reorder_exercises/', views_teachers.reorder_exercises, name='reorder_exercises'),
    path('api/modules/<int:module_id>/visibility/', views_teachers.set_module_visibility, name='set_module_visibility'),
    path('api/exercises/<int:exercise_id>/visibility/', views_teachers.set_exercise_visibility, name='set_exercise_visibility'),

    path('ai/authoring_assistant/', views_teachers.exercise_authoring_assistant, name='authoring_assistant'),
]

# Default export keeps backward compatibility (student-facing by default)
urlpatterns = students_urlpatterns