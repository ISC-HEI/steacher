from django.urls import path
from .consumers import QuizConsumer

websocket_urlpatterns = [
    path('ws/quiz/<int:cohort_id>/<int:module_id>/', QuizConsumer.as_asgi()),
]


