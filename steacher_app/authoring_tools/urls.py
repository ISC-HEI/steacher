from django.urls import path
from . import views

app_name = 'authoring_tools'

urlpatterns = [
    path('', views.upload_documents, name='upload'),
    path('<int:session_id>/review/', views.review_exercises, name='review'),
    path('exercises/<int:exercise_id>/approve/', views.approve_import_notes, name='approve_notes'),
    path('<int:session_id>/abort/', views.abort_session, name='abort'),
]
