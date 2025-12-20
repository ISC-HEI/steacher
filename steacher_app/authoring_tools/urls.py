from django.urls import path
from . import views

app_name = 'authoring_tools'

urlpatterns = [
    path('', views.upload_documents, name='upload'),
    path('<int:session_id>/analysis/', views.analysis_session, name='analysis'),
    path('<int:session_id>/create/', views.create_exercises, name='create_exercises'),
    path('<int:session_id>/review/', views.review_exercises, name='review'),
]
