from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model


class Course(models.Model):
    """
    A course that you teach, e.g. 'Intro to Python'.
    """
    name = models.CharField(max_length=200, help_text="The name/title of the course that will be displayed to the user.")
    description = models.TextField(blank=True, help_text="A short description of the course that will be displayed to the user.")
    llm_prompts = models.JSONField(blank=True, default=dict, help_text="LLM prompts per exercise type, e.g. {'turtle': 'Your prompt for turtle exercises...'}")
    visible = models.BooleanField(default=True, help_text="Whether the course is visible to students.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Module(models.Model):
    """
    A collection of @Exercise within a @Course.
    """
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    name = models.CharField(max_length=200, help_text="The name/title of the module that will be displayed to the user.")
    description = models.TextField(blank=True, help_text="A short description of the module that will be displayed to the user.")
    order = models.PositiveIntegerField(default=0, help_text="The order of the module within the course.")
    visible = models.BooleanField(default=True, help_text="Whether the module is visible to students.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['course', 'order']
        unique_together = ('course', 'order')


class Exercise(models.Model):
    """
    A single exercise within a @Module. Has different types (e.g. SQL, Python, multiple choice, etc.). 
    Inculdes metadata for the AI tutor to help the student, unit tests.
    """

    EXERCISE_TYPE_CHOICES = [
        ('python', 'Python'),
        ('multiple_choice', 'Multiple Choice'),
        ('sql', 'SQL'),
        ('turtle', 'Turtle'),
        ('open_question', 'Open Question'),
    ]

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='exercises')
    title = models.CharField(max_length=200, help_text="Title of the exercice; not displayed to the user.")
    description = models.TextField(blank=True, help_text="Description of the exercice; not displayed to the user.")
    exercise_type = models.CharField(
        max_length=50,
        choices=EXERCISE_TYPE_CHOICES,
        default='python',
        help_text="Type of the exercice, e.g. 'multiple_choice', 'text', 'turtle', etc."
    )
    order = models.PositiveIntegerField(default=0, help_text="The order of the exercice within the course.")
    exercise_data = models.JSONField(help_text="Contains fields like question, data-source, etc.")  # sent to frontend
    answer_data = models.JSONField(default=dict, help_text="Contains fields like expected_result, hints, etc.")  # backend only
    visible = models.BooleanField(default=True, help_text="Whether the exercise is visible to students.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.exercise_type})"

    class Meta:
        ordering = ['module', 'order']
        unique_together = ('module', 'order')


class Trace(models.Model):
    """
    Represents an attempt from a user at an @Exercise.
    Interactions will be stored in a list of @GuidanceLog objects.
    """
    # Foreign keys to link the log to a user and exercise
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='traces')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='traces')
    complete = models.BooleanField(default=False, help_text="True if the user has completed the exercise.")
    version = models.IntegerField(default=1, help_text="Version of the trace, can be used to track changes in the trace logic or prompt or eval version.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    system_prompt = models.TextField(null=True, blank=True, help_text="The system prompt sent to the LLM for this trace, if debugging is enabled.")

    def __str__(self):
        return f"Trace by {self.user.username} for '{self.exercise.title}'"

    class Meta:
        unique_together = ('user', 'exercise', 'version')



class GuidanceLog(models.Model):
    """
    Stores a single turn of interaction between a user and the AI tutor for a specific exercise.
    Each GuidanceLog entry references a @Trace.
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
    """
    A file associated with a course, e.g. a database file for an SQL exercise.
    """
    name = models.CharField(max_length=255, help_text="Filename like 'shop.sql', 'presentation.pptx'")
    description = models.TextField(null=True, blank=True, help_text="Optional description.")
    content = models.BinaryField(help_text="Store any file type as binary.")
    # LATER content_type = models.CharField(max_length=100, blank=True)  # MIME type
    # LATER file_size = models.PositiveIntegerField(null=True, blank=True)  # Size in bytes
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='assets'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} for course {self.course.name}"

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'course'],
                name='unique_name_per_course'
            ),
        ]


class TraceEval(models.Model):
    """
    Represents an evaluation of a user's trace for an exercise. Bound to a @Trace. Used to evaluate how the AI tutor is doing. 
    """
    trace = models.ForeignKey(Trace, on_delete=models.CASCADE, related_name='trace_evals')
    is_ok = models.BooleanField(null=True, help_text="Whether the trace is considered correct or not. Null means not evaluated.")
    feedback = models.TextField(blank=True, help_text="Feedback provided for this evaluation.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Evaluation for trace {self.trace.id} at {self.created_at}"

    class Meta:
        ordering = ['-created_at']


class StudentInvite(models.Model):
    """
    A student invite is an email address that has been invited to register as a student.
    """
    email = models.EmailField(unique=True, help_text="Lowercased")
    used = models.BooleanField(default=False)
    user = models.ForeignKey(get_user_model(), null=True, blank=True, on_delete=models.SET_NULL, related_name='student_invite')
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    registered_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.email} ({'used' if self.used else 'unused'})"

    def mark_used(self, user):
        self.used = True
        self.user = user
        self.registered_at = timezone.now()
        self.save(update_fields=['used', 'user', 'registered_at'])
