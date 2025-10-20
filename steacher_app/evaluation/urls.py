from django.urls import path
from . import views

app_name = 'evaluation'

urlpatterns = [
    path('<int:experiment_id>/evaluate/', views.experiment_evaluate, name='experiment_evaluate'),
    path('<int:experiment_id>/stats/', views.experiment_stats, name='experiment_stats'),
]

