from django.db import models
from django.contrib.auth.models import User


class Course(models.Model):
    name = models.CharField(max_length=200, help_text="The name/title of the course that will be displayed to the user.")
    description = models.TextField(blank=True, help_text="A short description of the course that will be displayed to the user.")
    llm_prompts = models.JSONField(blank=True, default=dict, help_text="LLM prompts per exercise type, e.g. {'turtle': 'Your prompt for turtle exercises...'}")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Exercise(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='exercises')
    title = models.CharField(max_length=200, help_text="Title of the exercice; not displayed to the user.")
    description = models.TextField(blank=True, help_text="Description of the exercice; not displayed to the user.")
    exercise_type = models.CharField(max_length=50, help_text="Type of the exercice, e.g. 'multiple_choice', 'text', 'turtle', etc.")
    order = models.PositiveIntegerField(default=0, help_text="The order of the exercice within the course.")
    exercise_data = models.JSONField(help_text="Contains fields like question, data-source, etc.")  # sent to frontend
    answer_data = models.JSONField(default=dict, help_text="Contains fields like expected_result, hints, etc.")  # backend only
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.exercise_type})"

    class Meta:
        ordering = ['course', 'order']
        unique_together = ('course', 'order')


class Trace(models.Model):
    """
    Represents an attempt from a user at an exercice.
    Interactions will be stored in a list of GuidanceLog objects.
    """
    # Foreign keys to link the log to a user and exercise
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='traces')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='traces')
    complete = models.BooleanField(default=False, help_text="True if the user has completed the exercise.")


class GuidanceLog(models.Model):
    """
    Stores a single turn of interaction between a user and the AI tutor for a specific exercise.
    Each GuidanceLog entry references a Trace.
    """
    trace = models.ForeignKey(Trace, on_delete=models.CASCADE, related_name='guidance_logs')

    # A single field to store the full interaction turn
    interaction = models.JSONField(
        help_text="Stores the user's submission and the LLM's response for a single turn."
    )

    # Timestamp for ordering the conversation
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Log for {self.trace.exercise.title} by {self.trace.user.username} at {self.submitted_at}, trace id: {self.trace.id}"

    class Meta:
        # Ensures logs are always ordered correctly when fetched
        ordering = ['submitted_at']


class ExerciceAsset(models.Model):
    name = models.CharField(max_length=255, help_text="Filename like 'shop.sql', 'presentation.pptx'")
    description = models.TextField(null=True, blank=True, help_text="Optional description.")
    content = models.BinaryField(help_text="Store any file type as binary.")
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
