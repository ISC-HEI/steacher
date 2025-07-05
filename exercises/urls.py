from django.urls import path
from . import views

app_name = 'exercises'

urlpatterns = [
    path('', views.exercise_list, name='list'),
    path('<int:pk>/', views.exercise_detail, name='detail'),
    path('<int:pk>/submit/', views.SubmitAnswerView.as_view(), name='submit'),
] 