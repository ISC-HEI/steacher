import html
from django import forms
from django.contrib import admin
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.utils.html import format_html, mark_safe
from django.db.models import Count
from .models import Exercise, Course, Module, ExerciceAsset, AttemptInteraction, Attempt, AttemptEval, UserInvite, ChatThread, Cohort, CohortMembership
from django_jsonform.widgets import JSONFormWidget

def format_interactions(attempt):
    """
    Formats the interactions for a given attempt into a nice HTML representation
    that looks like a chat dialogue.
    """
    logs = attempt.interactions.order_by('submitted_at')
    
    # Escape all user-provided content first
    username = html.escape(attempt.user.username)
    exercise_title = html.escape(attempt.exercise.title)
    # Use top-level question_i18n (fallback to any available language)
    q = ''
    try:
        q_map = getattr(attempt.exercise, 'question_i18n', {}) or {}
        if isinstance(q_map, dict):
            q = q_map.get('en') or next(iter(q_map.values()), '')
    except Exception:
        q = ''
    exercise_question = html.escape(q or 'No question provided.')
    
    html_output = f"<strong>User:</strong> {username}, <strong>Exercise:</strong> {exercise_title}<hr>"
    
    # Main container for the chat dialogue
    html_output += "<div style='padding: 10px; border: 1px solid #ccc; border-radius: 5px; background-color: #f9f9f9;'>"

    # add question text, looking like the llm response
    html_output += f"""
        <div style="display: flex; justify-content: flex-start; margin-bottom: 10px;">
            <div style="max-width: 80%; padding: 10px; border-radius: 15px; background-color: #fff; border: 1px solid #ddd;">
                <strong>Exercise Question:</strong> {exercise_question}
            </div>
        </div>
    """

    for i, log in enumerate(logs):
        interaction = log.interaction
        user_submission = interaction.get('user_submission', {})
        ai_response = interaction.get('llm_response', {})
        ai_metadata = ai_response.get('metadata', {})
        metadata = user_submission.get('metadata', {})

        # --- Build User Submission HTML (Right-aligned) ---
        submission_html = ""
        question = metadata.get('question')
        if question:
            escaped_question = html.escape(question)
            submission_html += f"<div><strong>Student's Question:</strong> {escaped_question}</div>"
        if metadata.get('action') == 'ask_hint':
            submission_html += "<div><em>Hint was requested.</em></div>"
        code = metadata.get('code')
        if code:
            language = html.escape(attempt.exercise.exercise_type)
            escaped_code = html.escape(code)
            submission_html += f'<pre class="line-numbers"><code class="language-{language}">{escaped_code}</code></pre>'
        
        if submission_html:
            html_output += f"""
                <div style="display: flex; justify-content: flex-end; margin-bottom: 10px;">
                    <div style="max-width: 80%; padding: 10px; border-radius: 15px; background-color: #dcf8c6;">
                        {submission_html}
                    </div>
                </div>
            """

        # --- Build AI Feedback HTML (Left-aligned) ---
        feedback = ai_response.get('content', '')
        if feedback:
            escaped_feedback = html.escape(feedback)
            ambiguity = ai_metadata.get('ambiguity')
            ambiguity_html = ""
            if ambiguity:
                ambiguity_items = "".join([f"<li>{html.escape(str(item))}</li>" for item in ambiguity])
                ambiguity_html = f"""
                    <div style="margin-top: 10px; padding: 10px; border: 1px solid #f0ad4e; border-radius: 5px; background-color: #fcf8e3;">
                        <strong>LLM Ambiguity:</strong>
                        <ul>{ambiguity_items}</ul>
                    </div>
                """
            html_output += f"""
                <div style="display: flex; justify-content: flex-start; margin-bottom: 10px;">
                    <div style="max-width: 80%; padding: 10px; border-radius: 15px; background-color: #fff; border: 1px solid #ddd;">
                        {escaped_feedback}
                        {ambiguity_html}
                    </div>
                </div>
            """
            if '<exercise_completed>' in feedback:
                html_output += "<div><em>Exercise marked as completed by the LLM.</em></div>"

    if not logs.exists():
        html_output += "<p>No interactions found for this attempt.</p>"
        
    html_output += "</div>" # Close main container
        
    # Use mark_safe instead of format_html since we've already escaped all user content
    return mark_safe(html_output)

LLM_PROMPTS_SCHEMA = {
    'type': 'object',
    'keys': {},
    'additionalProperties': {
        'type': 'string',
        'widget': 'textarea',
        'widget_attrs': {'rows': 20},
    }
}


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 1
    ordering = ('order',)
    show_change_link = True

class CourseAdminForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = '__all__'
        widgets = {
            'llm_prompts': JSONFormWidget(schema=LLM_PROMPTS_SCHEMA),
            'chat_prompt': forms.Textarea(attrs={'rows': 12}),
        }

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    form = CourseAdminForm
    list_display = ('name', 'created_at', 'updated_at')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ModuleInline]

 

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'course', 'order', 'view_exercises', 'created_at', 'updated_at')
    list_filter = ('course',)
    search_fields = ('name', 'description')
    ordering = ('course', 'order',)

    def view_exercises(self, obj):
        url = (
            reverse('admin:exercises_exercise_changelist')
            + f"?module__id__exact={obj.id}"
        )
        return format_html('<a href="{}">View</a>', url)
    view_exercises.short_description = 'View exercises'


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ('id', 'module', 'order', 'title', 'exercise_type', 'updated_at')
    list_filter = (('module', admin.RelatedOnlyFieldListFilter), 'module__course', 'exercise_type')
    search_fields = ('title', 'description')
    ordering = ('module', 'order')

class ExerciceAssetUploadForm(forms.ModelForm):
    upload_file = forms.FileField(
        label='Upload file',
        required=False,
        help_text='Upload a file to replace the stored content. Leave empty to keep current content.'
    )

    class Meta:
        model = ExerciceAsset
        fields = ('name', 'course', 'description')


@admin.register(ExerciceAsset)
class ExerciceAssetAdmin(admin.ModelAdmin):
    form = ExerciceAssetUploadForm
    list_display = ('name', 'course', 'description', 'created_at')
    list_filter = ('course',)
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at', 'content_size')

    def get_fieldsets(self, request, obj=None):
        return (
            (None, {
                'fields': ('name', 'course', 'description', 'upload_file', 'content_size')
            }),
            ('Timestamps', {
                'fields': ('created_at', 'updated_at'),
                'classes': ('collapse',)
            }),
        )

    def save_model(self, request, obj, form, change):
        uploaded = form.cleaned_data.get('upload_file')
        if uploaded:
            obj.content = uploaded.read()
        super().save_model(request, obj, form, change)

    def content_size(self, obj):
        if not obj or obj.content is None:
            return '0 bytes'
        try:
            return f"{len(obj.content)} bytes"
        except Exception:
            return 'Unknown'
    content_size.short_description = 'Content size'

@admin.register(AttemptInteraction)
class AttemptInteractionAdmin(admin.ModelAdmin):
    list_display = ('get_exercise', 'get_user', 'submitted_at')
    list_filter = ('attempt__user', 'attempt__exercise')
    date_hierarchy = 'submitted_at'
    ordering = ('-submitted_at',)

    def get_exercise(self, obj):
        return obj.attempt.exercise
    get_exercise.short_description = 'Exercise'

    def get_user(self, obj):
        return obj.attempt.user
    get_user.short_description = 'User'

class AttemptEvalInlineForm(forms.ModelForm):
    class Meta:
        model = AttemptEval
        fields = '__all__'
        widgets = {
            'is_ok': forms.RadioSelect(choices=[(True, 'Yes'), (False, 'No'), (None, 'Unknown')]),
        }

class AttemptEvalInline(admin.TabularInline):
    model = AttemptEval
    form = AttemptEvalInlineForm
    extra = 1
    fields = ('is_ok', 'feedback', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')

class HasEvaluationFilter(admin.SimpleListFilter):
    title = 'has evaluation'
    parameter_name = 'has_evaluation'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Yes'),
            ('no', 'No'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(evaluations__isnull=False).distinct()
        if self.value() == 'no':
            return queryset.filter(evaluations__isnull=True).distinct()

@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('id', 'version', 'exercise', 'user', 'complete', 'has_evaluation')
    list_filter = (('exercise', admin.RelatedOnlyFieldListFilter), ('user', admin.RelatedOnlyFieldListFilter), 'complete', 'version', HasEvaluationFilter)
    search_fields = ('exercise__title', 'user__username')
    inlines = [AttemptEvalInline]
    readonly_fields = ('id', 'version', 'display_interactions', 'display_full_prompt')
    ordering = ['id']

    fieldsets = (
        (None, {
            'fields': ('id', 'version', 'exercise', 'user', 'complete')
        }),
        ('Interactions', {
            'fields': ('display_interactions',),
        }),
        ('Full Prompt', {
            'fields': ('display_full_prompt',),
            'classes': ('collapse',)
        }),
    )

    change_form_template = "admin/exercises/attempt/change_form.html"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            eval_count=Count('evaluations')
        )
        return queryset

    def change_view(self, request, object_id, form_url='', extra_context=None):
        '''
        Add navigation arrows to the previous and next attempt.
        '''
        extra_context = extra_context or {}
        
        # Get the current attempt object
        obj = self.get_object(request, object_id)
        
        # Get the previous and next attempt objects by id
        prev_obj = Attempt.objects.filter(id__lt=obj.id).order_by('-id').first()
        next_obj = Attempt.objects.filter(id__gt=obj.id).order_by('id').first()
        
        extra_context['prev_obj'] = prev_obj
        extra_context['next_obj'] = next_obj
        
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context,
        )

    def response_change(self, request, obj):
        '''
        Adds navigation arrow to the next unevaluated attempt.
        '''
        if "_save_and_next" in request.POST:
            next_attempt = Attempt.objects.filter(evaluations__isnull=True, id__gt=obj.id).order_by('id').first()
            if next_attempt:
                return HttpResponseRedirect(reverse("admin:exercises_attempt_change", args=(next_attempt.id,)))
            else:
                self.message_user(request, "No more unevaluated attempts found.")
                return HttpResponseRedirect(reverse("admin:exercises_attempt_changelist"))
        return super().response_change(request, obj)

    def has_evaluation(self, obj):
        return obj.eval_count > 0
    has_evaluation.boolean = True
    has_evaluation.short_description = 'Has Evaluation?'
    has_evaluation.admin_order_field = 'eval_count'

    def display_interactions(self, obj):
        return format_interactions(obj)
    display_interactions.short_description = "Interactions"

    def display_full_prompt(self, obj):
        if not obj.system_prompt:
            return "No system prompt was saved for this attempt (debug mode was likely off)."

        full_prompt_str = f"----------------\n| ROLE:: SYSTEM | \n----------------\n{obj.system_prompt}\n\n"
        
        interactions = obj.interactions.order_by('submitted_at')
        for log in interactions:
            user_submission = log.interaction.get('user_submission')
            if user_submission:
                full_prompt_str += f"----------------\n| ROLE:: {user_submission.get('role', 'user')}  | \n----------------\n{user_submission.get('content', '')}\n\n"

            llm_response = log.interaction.get('llm_response')
            if llm_response:
                full_prompt_str += f"----------------\n| ROLE:: {llm_response.get('role', 'assistant')}| \n----------------\n{llm_response.get('content', '')}\n\n"
        
        return format_html("<pre style='max-width: 100%; white-space: pre-wrap; word-wrap: break-word;'>{}</pre>", full_prompt_str)
    display_full_prompt.short_description = "Full LLM Prompt"


@admin.register(AttemptEval)
class AttemptEvalAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'is_ok', 'created_at')
    list_filter = ('is_ok', 'attempt__exercise')
    search_fields = ('attempt__exercise__title', 'attempt__user__username', 'feedback')
    readonly_fields = ('created_at', 'updated_at', 'attempt_details_display')
    
    fieldsets = (
        (None, {
            'fields': ('attempt', 'is_ok', 'feedback')
        }),
        ('Attempt Details', {
            'fields': ('attempt_details_display',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['attempt'].queryset = Attempt.objects.filter(evaluations__isnull=True)
        return form

    def attempt_details_display(self, obj):
        if not obj.attempt:
            return "Select an attempt and save to see details."
        return format_interactions(obj.attempt)
    
    attempt_details_display.short_description = "Full Attempt History"


@admin.register(UserInvite)
class UserInviteAdmin(admin.ModelAdmin):
    list_display = ('email', 'used', 'user', 'created_at', 'registered_at')
    search_fields = ('email', 'user__username')
    list_filter = ('used',)
    readonly_fields = ('created_at', 'registered_at')


@admin.register(ChatThread)
class ChatThreadAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'title', 'messages_count', 'updated_at', 'created_at')
    list_filter = (('owner', admin.RelatedOnlyFieldListFilter),)
    search_fields = ('title', 'owner__username', 'owner__email')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-updated_at',)

    def messages_count(self, obj):
        try:
            return len(obj.messages or [])
        except Exception:
            return 0
    messages_count.short_description = 'Messages'


class CohortAdminForm(forms.ModelForm):
    student_usernames = forms.CharField(
        label='Add students by username',
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
        help_text='Comma, space, or newline separated usernames.'
    )

    class Meta:
        model = Cohort
        fields = '__all__'

    def save(self, commit=True):
        cohort = super().save(commit)
        raw = self.cleaned_data.get('student_usernames') or ''
        if not raw:
            return cohort
        # Normalize tokens
        separators = [',', '\n', '\r', '\t']
        for sep in separators:
            raw = raw.replace(sep, ' ')
        usernames = [u.strip() for u in raw.split(' ') if u.strip()]
        unique_usernames = []
        for u in usernames:
            if u not in unique_usernames:
                unique_usernames.append(u)

        from django.contrib.auth import get_user_model
        User = get_user_model()

        added, existing, missing = [], [], []
        for uname in unique_usernames:
            try:
                user = User.objects.get(username=uname)
            except User.DoesNotExist:
                missing.append(uname)
                continue
            # Use through model to avoid duplicates
            membership, created = CohortMembership.objects.get_or_create(cohort=cohort, student=user)
            if created:
                added.append(uname)
            else:
                existing.append(uname)

        # Defer messages to ModelAdmin.save_model where request is available
        self._bulk_add_result = {'added': added, 'existing': existing, 'missing': missing}
        return cohort


@admin.register(Cohort)
class CohortAdmin(admin.ModelAdmin):
    form = CohortAdminForm
    list_display = ('name', 'course', 'owner', 'code', 'created_at', 'updated_at')
    list_filter = ('course', ('owner', admin.RelatedOnlyFieldListFilter))
    search_fields = ('name', 'code', 'description')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('name', 'course', 'owner', 'code', 'description')
        }),
        ('Students', {
            'fields': ('student_usernames',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        result = getattr(form, '_bulk_add_result', None)
        if result:
            added = result.get('added') or []
            existing = result.get('existing') or []
            missing = result.get('missing') or []
            if added:
                self.message_user(request, f"Added {len(added)} students: {', '.join(added)}")
            if existing:
                self.message_user(request, f"Already in cohort ({len(existing)}): {', '.join(existing)}")
            if missing:
                self.message_user(request, f"Usernames not found ({len(missing)}): {', '.join(missing)}")
