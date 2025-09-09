from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from exercises.schemas import ExerciseData, AnswerData
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
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
    # Reverse link to all Trace rows that reference this Course as owner
    traces = GenericRelation('Trace', related_query_name='course_owner')
    # Course-level memberships (owner/editor/viewer)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='CourseMembership',
        through_fields=('course', 'user'),
        related_name='courses'
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

    @property
    def owner(self):
        membership = self.memberships.filter(role='owner').select_related('user').first()
        return membership.user if membership else None

    @property
    def editors(self):
        return self.members.filter(course_memberships__role__in=['owner', 'editor']).distinct()

    @property
    def viewers(self):
        return self.members.filter(course_memberships__role='viewer').distinct()


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
        constraints = [
            models.UniqueConstraint(
                fields=['course', 'order'],
                name='unique_module_order_per_course'
            ),
        ]
        indexes = [
            models.Index(fields=['course', 'visible'], name='module_course_visible_idx'),
        ]


class Cohort(models.Model):
    """
    A cohort groups students within a course. Owned by a teacher/admin.
    Members (students, teachers, owner) are connected via the CohortMembership through-model.
    """
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='cohorts')
    name = models.CharField(max_length=200, help_text="Human-friendly cohort name.")
    description = models.TextField(blank=True)
    code = models.CharField(max_length=32, null=True, blank=True, help_text="Optional short code for joining this cohort.")
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='CohortMembership',
        through_fields=('cohort', 'user'),
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

    @property
    def owner(self):
        """Returns the User object for the cohort's owner, or None."""
        membership = self.memberships.filter(role='owner').select_related('user').first()
        return membership.user if membership else None

    @property
    def teachers(self):
        """Returns a queryset of all teachers and owners for the cohort."""
        return self.members.filter(cohort_memberships__role__in=['teacher', 'owner']).distinct()

    @property
    def students(self):
        """Returns a queryset of all students for the cohort."""
        return self.members.filter(cohort_memberships__role='student').distinct()


class CohortMembership(models.Model):
    """
    Membership of a user in a cohort, with role and audit metadata.
    """
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('assistant', 'Assistant'),
        ('owner', 'Owner'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]

    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cohort_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    joined_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='cohort_members_added')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    def clean(self):
        """
        Called automatically by Django when the model is saved.
        Keep validation minimal; admin access is restricted to superusers only.
        """
        super().clean()

    class Meta:
        ordering = ['-joined_at']
        constraints = [
            # One membership per user per cohort
            models.UniqueConstraint(
                fields=['cohort', 'user'],
                name='unique_membership_per_cohort_user'
            ),
            # Only one owner per cohort
            models.UniqueConstraint(
                fields=['cohort'],
                condition=models.Q(role='owner'),
                name='unique_cohort_owner'
            ),
        ]
        indexes = [
            # Index for filtering by cohort and role
            models.Index(fields=['cohort', 'role'], name='cohort_role_idx'),
            # Additional common filters
            models.Index(fields=['user', 'role'], name='cm_user_role_idx'),
            models.Index(fields=['user', 'status', 'joined_at'], name='cm_user_status_joined_idx'),
            models.Index(fields=['cohort', 'status'], name='cm_cohort_status_idx'),
        ]

    def __str__(self):
        return f"{self.user} in {self.cohort} as {self.get_role_display()} ({self.status})"

    def save(self, *args, **kwargs):
        # Ensure model-level validation (including clean()) is applied on every save
        self.full_clean()
        return super().save(*args, **kwargs)


class CourseMembership(models.Model):
    """
    Course-level membership with roles: owner (single), editor, viewer.
    Used for authoring/viewing permissions at the course scope.
    """
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('editor', 'Editor'),
        ('viewer', 'Viewer'),
    ]

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='viewer')
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='course_members_added')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-joined_at']
        constraints = [
            models.UniqueConstraint(fields=['course', 'user'], name='unique_course_membership_per_user'),
            models.UniqueConstraint(
                fields=['course'],
                condition=models.Q(role='owner'),
                name='unique_course_owner'
            ),
        ]
        indexes = [
            models.Index(fields=['course', 'role'], name='course_role_idx'),
            models.Index(fields=['user', 'role'], name='course_user_role_idx'),
        ]

    def __str__(self):
        return f"{self.user} in course {self.course} as {self.get_role_display()}"


class Exercise(models.Model):
    """
    A single exercise within a @Module. Has different types (e.g. SQL, Python, open question, etc.). 
    Includes metadata for the AI tutor to help the student, unit tests.
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
        help_text="Type of the exercise, e.g. 'open_question', 'python', 'scala', 'sql', 'turtle', etc."
    )
    order = models.PositiveIntegerField(default=0, help_text="The order of the exercise within the course.")
    exercise_data = models.JSONField(help_text="Contains fields like data-source, etc.")  # sent to frontend
    answer_data = models.JSONField(default=dict, help_text="Contains fields like expected_result, hints, etc.")  # backend only
    visible = models.BooleanField(default=True, help_text="Whether the exercise is visible to students.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Reverse link to all Trace rows that reference this Exercise as owner (e.g., authoring)
    traces = GenericRelation('Trace', related_query_name='exercise_owner')

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
        constraints = [
            models.UniqueConstraint(
                fields=['module', 'order'],
                name='unique_exercise_order_per_module'
            ),
        ]
        indexes = [
            models.Index(fields=['module', 'visible'], name='exercise_module_visible_idx'),
        ]

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
    # Reverse link to all Trace rows that reference this Attempt as owner
    traces = GenericRelation('Trace', related_query_name='attempt_owner')

    objects = AttemptManager()

    def __str__(self):
        return f"Attempt by {self.user.username} for '{self.exercise.title}'"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'exercise', 'version'],
                name='unique_attempt_per_user_exercise_version'
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'updated_at'], name='attempt_user_updated_idx'),
            models.Index(fields=['user', 'complete', 'updated_at'], name='attempt_user_coplt_pdtd_idx'),
            models.Index(fields=['cohort', 'user'], name='attempt_cohort_user_idx'),
        ]

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

    def save(self, *args, **kwargs):
        # Ensure model-level validation (including clean()) is applied on every save
        self.full_clean()
        return super().save(*args, **kwargs)



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

    # Channel separates different interaction streams per owner
    CHANNEL_CHOICES = [
        ('exercise_guidance', 'Exercise Guidance'),
        ('learning_pathway', 'Learning Pathway'),
        ('authoring', 'Authoring'),
        ('study_chat', 'Study Chat'),
    ]
    channel = models.CharField(
        max_length=32,
        choices=CHANNEL_CHOICES,
        default='exercise_guidance',
        help_text="Logical stream for this trace (e.g., guidance vs. pathway vs. authoring)."
    )

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
            models.Index(fields=['content_type', 'object_id', 'channel'], name='trace_ct_oid_channel_idx'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['content_type', 'object_id', 'channel', 'rank_order'], name='unique_trace_rank_per_owner_channel'),
        ]


def create_trace_for(owner_obj, user, channel: str, **fields):
    """
    Create a Trace for the given owner_obj (e.g., Attempt, ChatThread) on the given
    channel, assigning a stable sequential rank_order within that channel.

    We compute next_rank as max(rank_order)+1 for the given channel inside a transaction and rely on the
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
                .filter(content_type=ct, object_id=oid, channel=channel)
                .aggregate(m=Max('rank_order'))['m']
            )
            # We do max()+1 so that rank_order remains contiguous and append-only
            next_rank = 0 if last is None else (int(last) + 1)
            try:
                return Trace.objects.create(
                    user=user,
                    content_type=ct,
                    object_id=oid,
                    channel=channel,
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
            .filter(content_type=ct, object_id=oid, channel=channel)
            .aggregate(m=Max('rank_order'))['m']
        )
        next_rank = 0 if last is None else (int(last) + 1)
        return Trace.objects.create(
            user=user,
            content_type=ct,
            object_id=oid,
            channel=channel,
            rank_order=next_rank,
            **fields
        )


class ExerciseAsset(models.Model):
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
        indexes = [
            models.Index(fields=['course', 'name'], name='asset_course_name_idx'),
        ]


class TraceEval(models.Model):
    """
    Evaluation of a specific @Trace. Used to evaluate AI response quality.
    Used either for students feedback on AI tutor (thumb-up/down) or for feedback with a comment from a teacher or admin.
    """
    trace = models.ForeignKey(Trace, on_delete=models.CASCADE, related_name='evaluations')
    is_ok = models.BooleanField(null=True, help_text="Whether this trace is considered correct or not. Null means not evaluated.")
    feedback = models.TextField(null=True, blank=True, help_text="Feedback provided for this evaluation.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Evaluation for trace {self.trace.id} at {self.created_at}"

    class Meta:
        ordering = ['-created_at']


class UserInvite(models.Model):
    """
    A user invite is an email address that has been invited to register as a student.
    """
    email = models.EmailField(unique=True, help_text="Lowercased")
    cohort = models.ForeignKey(Cohort, null=True, blank=True, on_delete=models.SET_NULL, related_name='user_invites', help_text="If set, the user will be added to this cohort upon registration.")
    used = models.BooleanField(default=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='user_invite')
    created_at = models.DateTimeField(auto_now_add=True)
    registered_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.email} ({'used' if self.used else 'unused'})"

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.email.lower()

    def mark_used(self, user):
        """
        Mark the invite as used and associate the user with it. Also add the user to the cohort, if any.
        """
        self.used = True
        self.user = user
        self.registered_at = timezone.now()
        self.save(update_fields=['used', 'user', 'registered_at'])
        if self.cohort:
            # Idempotently add user to the cohort. If they are already a member,
            # this does nothing.
            CohortMembership.objects.get_or_create(
                cohort=self.cohort,
                user=user,
                defaults={
                    'added_by': self.cohort.owner,
                    'role': 'student',
                }
            )

    def save(self, *args, **kwargs):
        # Normalize email to lowercase and enforce validation on every save
        if self.email:
            self.email = self.email.lower()
        self.full_clean()
        return super().save(*args, **kwargs)


class ChatThread(models.Model):
    """
    A standalone AI chat thread for a student. 
    Conversation is stored as @Trace rows (polymorphic, linked via GenericForeignKey).
    """
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_threads')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='chat_threads', help_text="Each chat thread is associated with a course.")
    title = models.CharField(max_length=255, help_text="Short title shown in the thread list.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Reverse link to all Trace rows that reference this ChatThread as owner (study chat)
    traces = GenericRelation('Trace', related_query_name='chatthread_owner')

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['owner', 'updated_at'], name='chathread_owner_updated_idx'),
            models.Index(fields=['owner', 'course', 'updated_at'], name='chat_owner_course_updated_idx'),
        ]

    def __str__(self):
        return f"ChatThread {self.id} by {self.owner} - {self.title}"
