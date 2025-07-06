from django.db import models
from django.contrib.auth.models import User


class Exercise(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    exercise_type = models.CharField(max_length=50)  # 'multiple_choice', 'text', 'turtle', etc.
    exercise_data = models.JSONField()  # Only question data (sent to frontend)
    answer_data = models.JSONField(default=dict)  # Answer data (backend only)
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


class ExerciceAsset(models.Model):
    name = models.CharField(max_length=255)  # Filename like 'shop.sql', 'presentation.pptx'
    description = models.TextField(null=True, blank=True) # optional description
    content = models.BinaryField()  # Store any file type as binary
    # LATER content_type = models.CharField(max_length=100, blank=True)  # MIME type
    # LATER file_size = models.PositiveIntegerField(null=True, blank=True)  # Size in bytes
    exercise = models.ForeignKey(
        Exercise, 
        # TODO check later how to handle this (cascade?)
        on_delete=models.SET_NULL, 
        related_name='assets',
        null=True, 
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        if self.exercise:
            return f"{self.name} for {self.exercise.title}"
        return f"{self.name} (standalone)"
    
    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'exercise'],
                name='unique_name_per_exercise'
            ),
            # TODO make unique on a Course
            # models.UniqueConstraint(
            #     fields=['name'],
            #     condition=models.Q(exercise__isnull=True),
            #     name='unique_standalone_asset_name'
            # )
        ]
