from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError


class Course(models.Model):
    """
    A course that you teach, e.g. 'Intro to Python'.
    """
    name = models.CharField(max_length=200, help_text="The name/title of the course that will be displayed to the user.")
    description = models.TextField(blank=True, help_text="A short description of the course that will be displayed to the user.")
    chat_prompt = models.TextField(blank=True, help_text="Chatbot-specific instructions for this course, when the user starts a chat thread.")
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


class Cohort(models.Model):
    """
    A cohort groups students within a course. Owned by a teacher/admin.
    Students are connected via the CohortMembership through-model.
    """
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='cohorts')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_cohorts')
    name = models.CharField(max_length=200, help_text="Human-friendly cohort name.")
    description = models.TextField(blank=True)
    code = models.CharField(max_length=32, null=True, blank=True, help_text="Optional short code for joining this cohort.")
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='CohortMembership',
        through_fields=('cohort', 'student'),
        related_name='cohorts'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.course.name})"

    class Meta:
        ordering = ['course', 'name']
        constraints = [
            models.UniqueConstraint(fields=['course', 'name'], name='unique_cohort_name_per_course'),
            models.UniqueConstraint(fields=['course', 'code'], name='unique_cohort_code_per_course'),
        ]


class CohortMembership(models.Model):
    """
    Membership of a student in a cohort, with audit metadata.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('removed', 'Removed'),
    ]

    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='memberships')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cohort_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='cohort_members_added')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    class Meta:
        unique_together = ('cohort', 'student')
        ordering = ['-joined_at']

    def __str__(self):
        return f"{self.student} in {self.cohort} ({self.status})"


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
        ('scala', 'Scala'),
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


class AttemptManager(models.Manager):
    def get_recent_for_user(self, user, count=None):
        """
        Gets recent attempts for a user.
        If count is None, gets only the most recent one.
        """
        query = (
            self.filter(user=user)
            .select_related('exercise__module__course')
            .order_by('-updated_at')
        )
        if count is None:
            return query.first()
        return query[:count]


class Attempt(models.Model):
    """
    Represents an attempt from a user at an @Exercise.
    Interactions will be stored in a list of @AttemptInteraction objects.
    """
    # Foreign keys to link the log to a user and exercise
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attempts')
    cohort = models.ForeignKey('Cohort', null=True, blank=True, on_delete=models.SET_NULL, related_name='attempts')
    complete = models.BooleanField(default=False, help_text="True if the user has completed the exercise.")
    version = models.IntegerField(default=1, help_text="Version of the attempt, can be used to track changes in the attempt logic or prompt or eval version.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    system_prompt = models.TextField(null=True, blank=True, help_text="The system prompt sent to the LLM for this attempt, if debugging is enabled.")

    objects = AttemptManager()

    def __str__(self):
        return f"Attempt by {self.user.username} for '{self.exercise.title}'"

    class Meta:
        unique_together = ('user', 'exercise', 'version')

    def clean(self):
        super().clean()
        if self.cohort:
            exercise_course_id = None
            try:
                exercise_course_id = self.exercise.module.course_id
            except Exception:
                pass
            if exercise_course_id and self.cohort.course_id != exercise_course_id:
                raise ValidationError("If set, cohort must belong to the same course as the exercise.")



class AttemptInteraction(models.Model):
    """
    Stores a single turn of interaction between a user and the AI tutor for a specific exercise.
    Each AttemptInteraction entry references a @Attempt.
    """
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='interactions')

    # A single field to store the full interaction turn
    interaction = models.JSONField(
        help_text="Stores the user's submission and the LLM's response for a single turn."
    )

    # Timestamp for ordering the conversation
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Interaction for {self.attempt.exercise.title} by {self.attempt.user.username} at {self.submitted_at}, attempt id: {self.attempt.id}"

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


class AttemptEval(models.Model):
    """
    Represents an evaluation of a user's attempt for an exercise. Bound to a @Attempt. Used to evaluate how the AI tutor is doing. 
    """
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='evaluations')
    is_ok = models.BooleanField(null=True, help_text="Whether the attempt is considered correct or not. Null means not evaluated.")
    feedback = models.TextField(blank=True, help_text="Feedback provided for this evaluation.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Evaluation for attempt {self.attempt.id} at {self.created_at}"

    class Meta:
        ordering = ['-created_at']


class UserInvite(models.Model):
    """
    A user invite is an email address that has been invited to register as a student.
    """
    email = models.EmailField(unique=True, help_text="Lowercased")
    used = models.BooleanField(default=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='user_invite')
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


class ChatThread(models.Model):
    """
    A standalone AI chat thread for a student. Stores the whole conversation as JSON.
    `messages` is an ordered list of objects like {"role": "user"|"assistant", "content": str, "created_at": iso str}.
    """
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_threads')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='chat_threads', help_text="Each chat thread is associated with a course.")
    title = models.CharField(max_length=255, help_text="Short title shown in the thread list.")
    messages = models.JSONField(default=list, blank=True, help_text="Ordered array of chat messages, just like in OpenAI's API.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"ChatThread {self.id} by {self.owner} - {self.title}"
