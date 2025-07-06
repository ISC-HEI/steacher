from django.urls import path
from . import views

app_name = 'exercises'

urlpatterns = [
    path('', views.exercise_list, name='exercise_list'),
    path('<int:pk>/', views.exercise_detail, name='exercise_detail'),
    path('<int:exercise_id>/<str:filename>', views.serve_asset, name='serve_asset'),
] 