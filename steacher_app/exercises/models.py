from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from functools import lru_cache
from exercises.schemas import ExerciseData, AnswerData
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import transaction, IntegrityError
from django.db.models import Max


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
    A single exercise within a @Module. Has different types (e.g. SQL, Python, open question, etc.). 
    Inculdes metadata for the AI tutor to help the student, unit tests.
    """

    EXERCISE_TYPE_CHOICES = [
        ('python', 'Python'),
        ('open_question', 'Open Question'),
        ('sql', 'SQL'),
        ('turtle', 'Turtle'),
        ('scala', 'Scala'),
    ]

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='exercises')
    # i18n fields (student-facing). Keys are language codes like 'en', 'fr', 'de'
    title_i18n = models.JSONField(default=dict, blank=True, help_text="Localized title strings by language code, e.g. {'en': '...', 'fr': '...'}")
    description_i18n = models.JSONField(default=dict, blank=True, help_text="Localized description strings by language code, e.g. {'en': '...', 'fr': '...'}")
    question_i18n = models.JSONField(default=dict, blank=True, help_text="Localized question (Markdown) by language code, e.g. {'en': '...', 'fr': '...'}")
    exercise_type = models.CharField(
        max_length=50,
        choices=EXERCISE_TYPE_CHOICES,
        default='python',
        help_text="Type of the exercice, e.g. 'open_question', 'python', 'scala', 'sql', 'turtle', etc."
    )
    order = models.PositiveIntegerField(default=0, help_text="The order of the exercice within the course.")
    exercise_data = models.JSONField(help_text="Contains fields like data-source, etc.")  # sent to frontend
    answer_data = models.JSONField(default=dict, help_text="Contains fields like expected_result, hints, etc.")  # backend only
    visible = models.BooleanField(default=True, help_text="Whether the exercise is visible to students.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        # Keep it simple: show the English title if set; otherwise a generic label
        title = (self.title_i18n or {}).get('en') or ''
        if not title:
            title = f"Exercise {self.id}"
        return f"{title} ({self.exercise_type})"

    # Backwards-compatible properties for templates/admin that referenced 'title'/'description'
    @property
    def title(self) -> str:
        # Expose English title for legacy template/admin usage
        return (self.title_i18n or {}).get('en', '')

    @property
    def description(self) -> str:
        # Expose English description for legacy template/admin usage
        return (self.description_i18n or {}).get('en', '')

    @property
    def exercise_data_obj(self) -> ExerciseData:
        """Returns the exercise_data field as a validated Pydantic object."""
        return ExerciseData.model_validate(self.exercise_data or {})

    @property
    def answer_data_obj(self) -> AnswerData:
        """Returns the answer_data field as a validated Pydantic object."""
        return AnswerData.model_validate(self.answer_data or {})

    class Meta:
        ordering = ['module', 'order']
        unique_together = ('module', 'order')

    @property
    def sequence_tuple(self):
        """
        Return a tuple (module_index, exercise_index) using 1-based indices
        derived from the persisted Module.order and Exercise.order fields.
        Falls back to (None, None) if unavailable.
        """
        try:
            module_order = getattr(self.module, 'order', None)
            exercise_order = getattr(self, 'order', None)
            if module_order is None or exercise_order is None:
                return (None, None)
            return (int(module_order) + 1, int(exercise_order) + 1)
        except Exception:
            return (None, None)

    @property
    def sequence_label(self) -> str:
        """
        Human-friendly label like "1.2" built from sequence_tuple.
        Returns an empty string if indices are not available.
        """
        module_idx, exercise_idx = self.sequence_tuple
        if module_idx and exercise_idx:
            return f"{module_idx}.{exercise_idx}"
        return ''


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
    Interactions are stored as @Trace rows (polymorphic, linked via GenericForeignKey).
    """
    # Foreign keys to link the log to a user and exercise
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attempts')
    cohort = models.ForeignKey('Cohort', null=True, blank=True, on_delete=models.SET_NULL, related_name='attempts')
    complete = models.BooleanField(default=False, help_text="True if the user has completed the exercise.")
    version = models.IntegerField(default=1, help_text="Version of the attempt, can be used to track changes in the attempt logic or prompt or eval version.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completion_feedback = models.JSONField(null=True, blank=True, help_text="The structured feedback and next exercise recommendations from the LLM upon completing an exercise.")

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



class Trace(models.Model):
    """
    Generic interaction trace between a user and an LLM, linked to any entity
    (e.g., Attempt, ChatThread) via a polymorphic key.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='traces')

    # Polymorphic link to the owning entity (Attempt, ChatThread, etc.)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # LLM/system message content
    system_prompt = models.TextField(null=True, blank=True, help_text="The system prompt sent to the LLM for this trace. Only set on the first trace.")

    # Assistant message
    assistant_content = models.TextField(blank=True, help_text="The assistant's response to the user's message.")
    assistant_metadata = models.JSONField(default=dict, blank=True, help_text="Metadata about the assistant's response, like the LLM response time, model, etc.")

    # User message
    user_content = models.TextField(blank=True, help_text="The user's message to the assistant.")
    user_metadata = models.JSONField(default=dict, blank=True, help_text="Metadata about the user's message, like the action, the question, the answer, the code, the output, the error message, etc.")

    rank_order = models.SmallIntegerField(default=0, help_text="The order of the trace within the owning entity's conversation.")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Trace for {self.user} on {self.content_type.app_label}.{self.content_type.model}#{self.object_id} (rank {self.rank_order})"

    class Meta:
        ordering = ['rank_order', 'id']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['content_type', 'object_id', 'rank_order'], name='unique_trace_rank_per_owner'),
        ]


def create_trace_for(owner_obj, user, **fields):
    """
    Create a Trace for the given owner_obj (e.g., Attempt, ChatThread) assigning a
    stable sequential rank_order.

    We compute next_rank as max(rank_order)+1 inside a transaction and rely on the
    unique constraint to guard against rare races. If a concurrent insert collides,
    we retry a few times.
    """
    ct = ContentType.objects.get_for_model(owner_obj, for_concrete_model=False)
    oid = getattr(owner_obj, 'pk')
    attempts = 3
    for _ in range(attempts):
        with transaction.atomic():
            last = (
                Trace.objects
                .filter(content_type=ct, object_id=oid)
                .aggregate(m=Max('rank_order'))['m']
            )
            # We do max()+1 so that rank_order remains contiguous and append-only
            next_rank = 0 if last is None else (int(last) + 1)
            try:
                return Trace.objects.create(
                    user=user,
                    content_type=ct,
                    object_id=oid,
                    rank_order=next_rank,
                    **fields
                )
            except IntegrityError:
                # Another process inserted the same rank concurrently; retry
                continue
    # Final attempt after retries
    with transaction.atomic():
        last = (
            Trace.objects
            .filter(content_type=ct, object_id=oid)
            .aggregate(m=Max('rank_order'))['m']
        )
        next_rank = 0 if last is None else (int(last) + 1)
        return Trace.objects.create(
            user=user,
            content_type=ct,
            object_id=oid,
            rank_order=next_rank,
            **fields
        )


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
