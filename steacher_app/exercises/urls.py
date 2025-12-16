from django.urls import path
from django.views.generic import TemplateView
from . import views_students, views_teachers, views_annotations, views_image_upload, views_mobile

app_name = 'exercises'

# Mobile URL patterns (PWA) - mounted at /m/ in project urls
mobile_urlpatterns = [
    # Dashboard
    path('', views_mobile.mobile_dashboard, name='mobile_dashboard'),
    # Install instructions
    path('install/', views_mobile.mobile_install, name='mobile_install'),
    # Exercise
    path('exercise/<int:exercise_id>/', views_mobile.mobile_exercise, name='mobile_exercise'),
    # Voice transcription
    path('voice-transcribe/', views_mobile.mobile_voice_transcribe, name='mobile_voice_transcribe'),
    # Authentication (Magic Link Only)
    path('auth/request-link/', views_mobile.mobile_auth_request_link, name='mobile_auth_request_link'),
    path('auth/send-link/', views_mobile.mobile_auth_send_link, name='mobile_auth_send_link'),
]

# Students' URL patterns
students_urlpatterns = [
    path('about/', TemplateView.as_view(template_name="exercises/students/about.html"), name='about'),
    path('dashboard/', views_students.dashboard, name='dashboard'),
    path('chat/', views_students.chat_home, name='chat_home'),
    path('chat/threads/', views_students.chat_threads, name='chat_threads'),
    path('chat/threads/<int:thread_id>/', views_students.chat_thread_detail, name='chat_thread_detail'),
    path('chat/threads/<int:thread_id>/send/', views_students.chat_thread_send, name='chat_thread_send'),
    path('chat/threads/<int:thread_id>/delete/', views_students.chat_thread_delete, name='chat_thread_delete'),
    path('courses/<int:pk>/', views_students.course_detail, name='course_detail'),
    path('courses/<int:pk>/export/', views_students.export_course_data, name='export_course_data'),
    # Image upload / token endpoints
    path('image/upload-token/', views_image_upload.generate_upload_token, name='generate_upload_token'),
    path('image/<str:token>/', views_image_upload.serve_trace_image, name='serve_trace_image'),
    path('image-highlighted/<str:token>/', views_image_upload.serve_highlighted_image, name='serve_highlighted_image'),
    path('image/image-status/<str:token>/', views_image_upload.image_status, name='image_status'),
    # Mobile (unauthenticated) upload page and submit endpoint
    path('upload/<str:token>/', views_image_upload.mobile_upload_page, name='mobile_upload_page'),
    path('upload/<str:token>/submit/', views_image_upload.mobile_upload_submit, name='mobile_upload_submit'),
    # More specific patterns first to avoid conflicts
    path('<int:exercise_id>/attempts/<int:attempt_id>/guidance/', views_students.get_guidance, name='get_guidance'),
    path('api/attempts/<int:attempt_id>/recommend_pathway/', views_students.recommend_learning_pathway, name='recommend_learning_pathway'),
    path('<int:exercise_id>/delete_answers/', views_students.delete_user_answers, name='delete_user_answers'),
    path('<int:exercise_id>/<str:filename>', views_students.serve_asset, name='serve_asset'),
    path('api/scala/execute/', views_students.scala_execute, name='scala_execute'),
    path('api/trace-eval/', views_students.trace_eval_create, name='trace_eval_create'),
    # Generic pattern last
    path('<int:pk>/', views_students.exercise_detail, name='exercise_detail'),
    # Quiz waiting room (students)
    path('cohorts/<int:cohort_id>/quiz/waiting/', views_students.quiz_waiting, name='quiz_waiting'),
    # Quiz APIs for waiting room
    path('api/quiz/<int:cohort_id>/overview/', views_students.quiz_overview, name='quiz_overview'),
    path('api/quiz/<int:cohort_id>/presence_heartbeat/', views_students.quiz_presence_heartbeat, name='quiz_presence_heartbeat'),
]

# Teachers' URL patterns (namespaced at project level under 'teachers')
teachers_urlpatterns = [
    path('dashboard/', views_teachers.dashboard, name='dashboard'),
    path('cohorts/<int:pk>/', views_teachers.cohort_detail, name='cohort_detail'),
    path('cohorts/<int:cohort_id>/students/<int:student_id>/', views_teachers.cohort_student_detail, name='cohort_student_detail'),
    path('cohorts/<int:cohort_id>/exercises/<int:exercise_id>/', views_teachers.cohort_exercise_detail, name='cohort_exercise_detail'),
    path('courses/<int:pk>/', views_teachers.course_detail, name='course_detail'),
    path('courses/<int:pk>/edit/', views_teachers.course_edit, name='course_edit'),
    path('courses/<int:course_pk>/modules/<int:module_pk>/add_exercise/', views_teachers.exercise_form, name='exercise_add'),
    path('courses/<int:course_pk>/edit_exercise/<int:exercise_pk>/', views_teachers.exercise_form, name='exercise_edit'),
    # Analytics routes
    path('courses/<int:course_id>/analytics/', views_teachers.course_analytics_dashboard, name='course_analytics_dashboard'),
    path('exercises/<int:exercise_id>/analytics/', views_teachers.exercise_analytics_detail, name='exercise_analytics_detail'),

    path('api/reorder_modules/', views_teachers.reorder_modules, name='reorder_modules'),
    path('api/reorder_exercises/', views_teachers.reorder_exercises, name='reorder_exercises'),
    path('api/modules/<int:module_id>/visibility/', views_teachers.set_module_visibility, name='set_module_visibility'),
    path('api/modules/create/', views_teachers.create_module, name='create_module'),
    path('api/exercises/<int:exercise_id>/visibility/', views_teachers.set_exercise_visibility, name='set_exercise_visibility'),
    path('api/exercises/<int:exercise_id>/duplicate/', views_teachers.duplicate_exercise, name='duplicate_exercise'),
    path('api/exercises/<int:exercise_id>/delete/', views_teachers.delete_exercise, name='delete_exercise'),

    path('ai/authoring_assistant/', views_teachers.exercise_authoring_assistant, name='authoring_assistant'),
    path('ai/translate_i18n/', views_teachers.translate_i18n, name='translate_i18n'),

    # Quiz control UI (teacher)
    path('cohorts/<int:cohort_id>/quiz/<int:module_id>/', views_teachers.quiz_control, name='quiz_control'),
    # Quiz results API (teacher)
    path('api/quiz/<int:cohort_id>/<int:module_id>/exercises/<int:exercise_id>/results/', views_teachers.quiz_results_api, name='quiz_results_api'),
    # Quiz reset API (teacher)
    path('api/quiz/<int:cohort_id>/<int:module_id>/reset/', views_teachers.reset_quiz, name='quiz_reset'),
    
    # Annotation routes
    path('exercises/<int:exercise_id>/annotate/', views_annotations.annotate_exercise_entry, name='annotate_exercise'),
    path('exercises/<int:exercise_id>/annotate/<int:attempt_id>/', views_annotations.annotate_attempt, name='annotate_attempt'),
    
    # Module import/export
    path('modules/<int:module_id>/export/', views_teachers.export_module, name='export_module'),
    path('courses/<int:course_id>/import-module/', views_teachers.import_module, name='import_module'),
]

# Default export is student-facing patterns (exercises/ prefix)
urlpatterns = students_urlpatterns