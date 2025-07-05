from django.db import models
from django.contrib.auth.models import User


class Exercise(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    exercise_type = models.CharField(max_length=50)  # 'multiple_choice', 'text', 'turtle', etc.
    exercise_data = models.JSONField()  # All exercise-specific data
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.exercise_type})"

    class Meta:
        ordering = ['created_at']


class Answer(models.Model):
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='answers')
    user_answer = models.JSONField()  # Flexible answer format
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_correct = models.BooleanField(null=True, blank=True)  # Can be calculated on frontend

    def __str__(self):
        return f"Answer for {self.exercise.title} at {self.submitted_at}"

    class Meta:
        ordering = ['-submitted_at']
