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
    course_prompt = models.TextField(blank=True, help_text="Course-level prompt for this specific course. Will be added at the end of the system prompt for all exercises in this course. It may contain information about the course contents, objectives, target audience, etc. You can also include a large amount of information about the course content itself (e.g. a summary of 5k words), so that in its answers, the AI will refer to parts of the course content itself. Also, you may include which notations to use, which concepts to avoid, etc.")
    override_system_prompt = models.TextField(blank=True, help_text="Override the default system prompt used by the AI tutor for exercises in this course. Leave empty to use the global default (recommended).")
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
    is_quiz = models.BooleanField(default=False, help_text="Whether this module is a quiz module.")
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

    def save(self, *args, **kwargs):
        """
        On create, if no explicit order is provided (left as 0/None),
        assign order = max(order) + 1 within the same course.

        This keeps module ordering contiguous without requiring manual input.
        """
        if self.pk is None and (getattr(self, 'order', None) in (None, 0)) and getattr(self, 'course_id', None):
            # Compute next order inside a transaction to minimize race risk
            for _ in range(2):  # try at most twice in the rare case of a concurrent insert
                with transaction.atomic():
                    last = (
                        Module.objects
                        .filter(course_id=self.course_id)
                        .aggregate(m=Max('order'))['m']
                    )
                    self.order = 0 if last is None else (int(last) + 1)
                    try:
                        return super().save(*args, **kwargs)
                    except IntegrityError:
                        # Another process inserted with the same order; retry once
                        continue
        return super().save(*args, **kwargs)

    @property
    def visible_exercises(self):
        return self.exercises.filter(visible=True)


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


class TraceImage(models.Model):
    """
    Image uploaded for a Trace, typically a photo of handwritten work.
    Stored as binary data in the database.
    """
    trace = models.ForeignKey(
        'Trace',
        on_delete=models.CASCADE,
        related_name='images',
        null=True, 
        blank=True
    )
    image = models.BinaryField(help_text="Store image as binary data", null=True, blank=True)
    upload_token = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text="Unique token for unauthenticated upload"
    )
    uploaded_at = models.DateTimeField(null=True, blank=True, help_text="When the image was uploaded")
    created_at = models.DateTimeField(auto_now_add=True)
    image_type = models.CharField(
        max_length=50,
        default='image/jpeg',
        help_text="MIME type of the image"
    )
    token_expires_at = models.DateTimeField(help_text="When the upload token expires")
    file_size = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Size in bytes"
    )
    next_token = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        help_text="Token for next photo in upload chain"
    )
    chain_position = models.IntegerField(
        default=0,
        help_text="Position in upload chain (0=first, max 2 for 3 photos total)"
    )
    highlight_bboxes = models.JSONField(
        default=list,
        blank=True,
        help_text="List of bounding boxes with highlighting info. Format: [{'bbox': [x0, y0, x1, y1], 'color': 'yellow'}, ...]"
    )

    @property
    def image_bytes(self) -> bytes:
        """
        Returns the image data as bytes, handling the conversion from memoryview if needed.
        This ensures consistent bytes type for external APIs like Gemini.
        """
        if not self.image:
            return b''
        
        if isinstance(self.image, memoryview):
            return self.image.tobytes()
        elif isinstance(self.image, bytes):
            return self.image
        else:
            return bytes(self.image)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['trace', 'created_at']),
            models.Index(fields=['upload_token']),
        ]

    def __str__(self):
        return f"TraceImage {self.id} for attempt {self.trace_id}"


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
    order = models.PositiveIntegerField(default=0, help_text="The order of the exercise within its module.")
    exercise_data = models.JSONField(help_text="Contains fields like data-source, etc.")  # sent to frontend
    answer_data = models.JSONField(default=dict, help_text="Contains fields like expected_result, hints, etc.")  # backend only
    visible = models.BooleanField(default=True, help_text="Whether the exercise is visible to students.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    allow_image_upload = models.BooleanField(default=False) # user can input images
    
    # Draft exercise fields (for bulk import feature)
    is_draft = models.BooleanField(default=False, help_text="Whether this exercise is a draft (hidden from students until published).")
    draft_notes = models.TextField(blank=True, help_text="AI-generated notes about this exercise (what worked, questions, suggestions). Format is a 'full text', not structured like a json.")

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
    asked_for_solution = models.BooleanField(default=False, help_text="True if the user has asked for the solution.")
    version = models.IntegerField(default=1, help_text="Version of the attempt, can be used to track changes in the attempt logic or prompt or eval version.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
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
    system_prompt = models.TextField(null=True, blank=True, help_text="The system prompt sent to the LLM for this trace. Only set on the first trace. It's kept in this Trace for reference & debugging purposes.")

    # Assistant message
    assistant_content = models.JSONField(default=dict, blank=True, help_text="""Complete JSON response of the assistant. Keys: 
- transcript: string, optional (if the user uploaded a picture of his work), the complete LaTeX retranscription of the student worksheet picture that you received, **this must be written in valid LaTeX format**.
- error_desc: string, a concise description of the mistakes made by the student that you spotted.
- guidance_text: string, the guidance text to help the student with his exercise.
""")
    assistant_metadata = models.JSONField(default=dict, blank=True, help_text="Metadata about the assistant's response, like the LLM response time, model, etc.")

    # User message
    user_content = models.TextField(blank=True, help_text="The user's message to the assistant.")
    user_metadata = models.JSONField(default=dict, blank=True, help_text="Metadata about the user's message, like the action, the question, the answer, the code, the output, the error message, etc.")

    rank_order = models.SmallIntegerField(default=0, help_text="The order of the trace within the owning entity's conversation.")
    created_at = models.DateTimeField(auto_now_add=True)

    def assistant_content_text(self) -> str:
        """
        Utility function to convert the assistant_content dictionary to a text string.
        """
        text = ""
        if self.assistant_content.get('guidance_text'):
            text += f"\n\nGuidance Text: {self.assistant_content['guidance_text']}"
        if self.assistant_content.get('transcript'):
            text += f"\n\nTranscript: {self.assistant_content['transcript']}"
        if self.assistant_content.get('error_desc'):
            text += f"\n\nError Description: {self.assistant_content['error_desc']}"
        return text

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


class QuizLog(models.Model):
    """
    Log of completed quiz sessions for analytics and tracking.
    """
    cohort = models.ForeignKey('Cohort', on_delete=models.CASCADE, related_name='quiz_logs')
    module = models.ForeignKey('Module', on_delete=models.CASCADE, related_name='quiz_logs')
    completed_at = models.DateTimeField(auto_now_add=True)
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    student_count = models.IntegerField(help_text="Number of students who participated")

    class Meta:
        ordering = ['-completed_at']
        indexes = [
            models.Index(fields=['cohort', 'module'], name='quiz_log_cohort_module_idx'),
            models.Index(fields=['completed_at'], name='quiz_log_completed_idx'),
        ]

    def __str__(self):
        return f"Quiz {self.module.name} for {self.cohort.name} completed at {self.completed_at}"


class AttemptEval(models.Model):
    """
    Teacher evaluation of a student's attempt at an exercise.
    Used for manual annotation during the "Analyze" phase of evaluation lifecycle.
    """
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='evaluations')
    is_ok = models.BooleanField(null=True, blank=True, help_text="True=good, False=bad, None=unknown")
    feedback = models.TextField(blank=True, help_text="Free-form annotation notes")
    annotator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='attempt_annotations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['attempt', 'annotator'], name='unique_eval_per_annotator_attempt')
        ]
        indexes = [
            models.Index(fields=['annotator', 'created_at'], name='attempteval_annotator_idx'),
        ]

    def __str__(self):
        status = "good" if self.is_ok is True else ("bad" if self.is_ok is False else "unknown")
        return f"Eval of attempt {self.attempt_id} by {self.annotator}: {status}"


def localized_name(obj, field_name: str, user, lang: str=None) -> str:
    """
    Helper function to return the localized name of the given object's i18n field for the given user.
    If lang is provided, use it instead of the user's preferred language.
    """
    if not isinstance(obj, models.Model):
        return ''
    try:
        return getattr(obj, field_name).get(lang or getattr(user, 'preferred_language', 'en'), getattr(obj, field_name).get('en', ''))
    except Exception:
        if isinstance(getattr(obj, field_name), dict):
            return getattr(obj, field_name).get('en', '')
        return ''


class MobileAuthToken(models.Model):
    """
    Token for mobile authentication via magic link email.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mobile_auth_tokens')
    token = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    first_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token', 'used', 'expires_at']),
        ]
    
    def __str__(self):
        return f"Magic link token for {self.user.username}"