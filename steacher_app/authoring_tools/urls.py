from django.urls import path
from . import views

app_name = 'authoring_tools'

urlpatterns = [
    # Landing page with course selection
    path('', views.question_generator_landing, name='landing'),
    
    # Start new session
    path('start/', views.start_question_generator, name='start'),
    
    # Session-specific chat interface
    path('session/<int:session_id>/', views.question_generator_chat, name='chat'),
    path('session/<int:session_id>/message/', views.chat_message, name='chat_message'),
    path('session/<int:session_id>/upload/', views.upload_file, name='upload_file'),
    path('session/<int:session_id>/file/<int:file_id>/delete/', views.delete_file, name='delete_file'),
    path('session/<int:session_id>/build/', views.build_exercises, name='build_exercises'),
    path('session/<int:session_id>/traces/', views.get_session_traces, name='get_traces'),
    path('session/<int:session_id>/review/', views.review_exercises, name='review'),
    path('session/<int:session_id>/abort/', views.abort_session, name='abort'),
    
    # Exercise management
    path('exercises/<int:exercise_id>/approve/', views.approve_import_notes, name='approve_notes'),
]
