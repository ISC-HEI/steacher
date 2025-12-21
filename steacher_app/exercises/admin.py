import html
from django import forms
from django.contrib import admin
from django.db import IntegrityError
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.utils.html import format_html, mark_safe
from django.db.models import Count
from .models import Exercise, Course, Module, ExerciseAsset, Attempt, UserInvite, ChatThread, Cohort, CohortMembership, Trace, TraceEval, CourseMembership, QuizLog, TraceImage, MobileAuthToken
from django_jsonform.widgets import JSONFormWidget

# Customize Django admin titles
admin.site.site_header = "Steacher Administration"
admin.site.site_title = "Steacher Administration"
admin.site.index_title = " "

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
            html_output += f"""
                <div style="display: flex; justify-content: flex-start; margin-bottom: 10px;">
                    <div style="max-width: 80%; padding: 10px; border-radius: 15px; background-color: #fff; border: 1px solid #ddd;">
                        {escaped_feedback}
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

class CourseMembershipInline(admin.TabularInline):
    model = CourseMembership
    fk_name = 'course'
    extra = 0
    autocomplete_fields = ['user']
    fields = ('user', 'role', 'joined_at', 'added_by')
    readonly_fields = ('joined_at',)
    verbose_name = 'Member'
    verbose_name_plural = 'Members'

class CourseAdminForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = '__all__'
        widgets = {
            'llm_prompts': JSONFormWidget(schema=LLM_PROMPTS_SCHEMA),
            'chat_prompt': forms.Textarea(attrs={'rows': 12}),
            'course_prompt': forms.Textarea(attrs={'rows': 12}),
            'override_system_prompt': forms.Textarea(attrs={'rows': 20}),
        }

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    form = CourseAdminForm
    list_display = ('id', 'name', 'owner', 'created_at', 'updated_at')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [CourseMembershipInline, ModuleInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'visible')
        }),
        ('AI Prompts', {
            'fields': ('course_prompt', 'chat_prompt', 'override_system_prompt', 'llm_prompts')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Ensure added_by is set for any newly created memberships without it
        CourseMembership.objects.filter(course=obj, added_by__isnull=True).update(added_by=request.user)

    def save_formset(self, request, form, formset, change):
        try:
            instances = formset.save(commit=False)
            # Process deletions first so uniqueness constraints don't interfere
            for obj in getattr(formset, 'deleted_objects', []):
                try:
                    obj.delete()
                except Exception:
                    continue
            for obj in instances:
                if isinstance(obj, CourseMembership) and not getattr(obj, 'added_by_id', None):
                    obj.added_by = request.user
                obj.save()
            formset.save_m2m()
        except IntegrityError:
            raise forms.ValidationError('Only one owner is allowed per course. Demote the existing owner before assigning a new one.')

 

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


class ExerciseAdminForm(forms.ModelForm):
    course_module = forms.ModelChoiceField(
        queryset=Module.objects.none(),
        required=False,
        label="Module (from same course)"
    )

    class Meta:
        model = Exercise
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['module'].label = "Module (from any course)"

        if self.instance and self.instance.pk and self.instance.module:
            course = self.instance.module.course
            self.fields['course_module'].queryset = Module.objects.filter(course=course).order_by('order')
            self.fields['course_module'].initial = self.instance.module
        else:
            self.fields['course_module'].widget.attrs['disabled'] = True
            self.fields['course_module'].help_text = "Select a module and save to enable this field."

    def clean(self):
        cleaned_data = super().clean()
        course_module = cleaned_data.get('course_module')

        if course_module:
            cleaned_data['module'] = course_module

        return cleaned_data


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    form = ExerciseAdminForm
    list_display = ('id', 'module', 'order', 'title', 'exercise_type', 'last_edited_by', 'updated_at')
    list_filter = (('module', admin.RelatedOnlyFieldListFilter), 'module__course', 'exercise_type')
    search_fields = ('title_i18n', 'description_i18n', 'question_i18n')
    ordering = ('module', 'order')

    fieldsets = (
        (None, {
            'fields': (
                'course_module',
                'module',
                'order',
                'title_i18n',
                'description_i18n',
                'question_i18n',
                'exercise_type',
                'exercise_data',
                'answer_data',
                'visible'
            )
        }),
    )

    def last_edited_by(self, obj):
        try:
            trace = (
                obj.traces
                .filter(channel='authoring')
                .select_related('user')
                .order_by('-id')
                .first()
            )
            if not trace or not getattr(trace, 'user', None):
                return ''
            # Prefer username; fallback to email or string repr
            username = getattr(trace.user, 'username', None)
            if username:
                return username
            email = getattr(trace.user, 'email', None)
            if email:
                return email
            return str(trace.user)
        except Exception:
            return ''
    last_edited_by.short_description = 'Last edited by'

class ExerciseAssetUploadForm(forms.ModelForm):
    upload_file = forms.FileField(
        label='Upload file',
        required=False,
        help_text='Upload a file to replace the stored content. Leave empty to keep current content.'
    )

    class Meta:
        model = ExerciseAsset
        fields = ('name', 'course', 'description')


@admin.register(ExerciseAsset)
class ExerciseAssetAdmin(admin.ModelAdmin):
    form = ExerciseAssetUploadForm
    list_display = ('name', 'course', 'description', 'content_size', 'created_at')
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

@admin.register(Trace)
class TraceAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'content_type', 'object_id', 'channel', 'rank_order', 'created_repr', 'view_related_object')
    list_filter = (('user', admin.RelatedOnlyFieldListFilter), ('content_type', admin.RelatedOnlyFieldListFilter), 'channel')
    search_fields = ('id', 'user__username', 'user__email')
    ordering = ('-id',)
    readonly_fields = ('view_related_object_link', 'created_at')

    def created_repr(self, obj):
        try:
            if obj.created_at:
                return obj.created_at.strftime('%Y-%m-%d %H:%M:%S')
            return None
        except Exception:
            return None
    created_repr.short_description = 'Created at'

    def view_related_object(self, obj):
        """Display a link to the related object (e.g., Attempt) in the list view."""
        if not obj or not obj.content_type or not obj.object_id:
            return '-'
        try:
            model_class = obj.content_type.model_class()
            if model_class.__name__ == 'Attempt':
                url = reverse('admin:exercises_attempt_change', args=[obj.object_id])
                return format_html('<a href="{}">Attempt #{}</a>', url, obj.object_id)
            elif model_class.__name__ == 'ChatThread':
                url = reverse('admin:exercises_chatthread_change', args=[obj.object_id])
                return format_html('<a href="{}">Chat #{}</a>', url, obj.object_id)
            else:
                return f"{model_class.__name__} #{obj.object_id}"
        except Exception:
            return '-'
    view_related_object.short_description = 'Related Object'

    def view_related_object_link(self, obj):
        """Display a link to the related object in the detail view."""
        if not obj or not obj.content_type or not obj.object_id:
            return 'No related object'
        try:
            model_class = obj.content_type.model_class()
            if model_class.__name__ == 'Attempt':
                url = reverse('admin:exercises_attempt_change', args=[obj.object_id])
                return format_html('<a href="{}">View Attempt #{}</a>', url, obj.object_id)
            elif model_class.__name__ == 'ChatThread':
                url = reverse('admin:exercises_chatthread_change', args=[obj.object_id])
                return format_html('<a href="{}">View Chat Thread #{}</a>', url, obj.object_id)
            else:
                return f"{model_class.__name__} #{obj.object_id}"
        except Exception as e:
            return f'Error: {str(e)}'
    view_related_object_link.short_description = 'Related Object'

    fieldsets = (
        (None, {
            'fields': ('user', 'content_type', 'object_id', 'view_related_object_link', 'channel', 'rank_order', 'created_at')
        }),
        ('Content', {
            'fields': ('system_prompt', 'user_content', 'assistant_content')
        }),
        ('Metadata', {
            'fields': ('user_metadata', 'assistant_metadata')
        }),
    )


class HasEvaluationFilter(admin.SimpleListFilter):
    title = 'has evaluation'
    parameter_name = 'has_evaluation'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Yes'),
            ('no', 'No'),
        )

    def queryset(self, request, queryset):
        # With TraceEval decoupled from Attempt, this filter is no longer applicable.
        return queryset


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('id', 'version', 'exercise_link', 'user', 'complete')
    list_filter = (('exercise', admin.RelatedOnlyFieldListFilter), ('user', admin.RelatedOnlyFieldListFilter), 'complete', 'version')
    search_fields = ('id', 'exercise__title_i18n', 'user__username')
    inlines = []
    readonly_fields = ('id', 'version', 'exercise_admin_link')
    ordering = ['id']

    fieldsets = (
        (None, {
            'fields': ('id', 'version', 'exercise', 'exercise_admin_link', 'user', 'complete')
        }),
        # Interactions display removed to keep admin minimal for traces
    )

    def exercise_link(self, obj):
        """Display a clickable link to the Exercise in the list view."""
        if not obj or not obj.exercise:
            return '-'
        try:
            url = reverse('admin:exercises_exercise_change', args=[obj.exercise.id])
            return format_html('<a href="{}">{}</a>', url, obj.exercise.title)
        except Exception:
            return str(obj.exercise)
    exercise_link.short_description = 'Exercise'
    exercise_link.admin_order_field = 'exercise'

    def exercise_admin_link(self, obj):
        """Display a clickable link to the Exercise in the detail view."""
        if not obj or not obj.exercise:
            return 'No exercise'
        try:
            url = reverse('admin:exercises_exercise_change', args=[obj.exercise.id])
            return format_html('<a href="{}">View Exercise: {}</a>', url, obj.exercise.title)
        except Exception as e:
            return f'Error: {str(e)}'
    exercise_admin_link.short_description = 'Exercise'

    change_form_template = "admin/exercises/attempt/change_form.html"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
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

    # Evaluation display removed as evaluations are now linked to Trace

    # Removed custom interactions/prompt display for simplicity


class TraceEvalAdminForm(forms.ModelForm):
    class Meta:
        model = TraceEval
        fields = '__all__'
        widgets = {
            'is_ok': forms.RadioSelect(choices=[(True, 'Yes'), (False, 'No'), (None, 'Unknown')]),
        }


@admin.register(TraceEval)
class TraceEvalAdmin(admin.ModelAdmin):
    form = TraceEvalAdminForm
    list_display = ('trace', 'is_ok', 'feedback', 'created_at')
    list_filter = ('is_ok', 'trace__channel')
    search_fields = ('trace__user__username', 'feedback')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(UserInvite)
class UserInviteAdmin(admin.ModelAdmin):
    list_display = ('email', 'used', 'user', 'created_at', 'registered_at')
    search_fields = ('email', 'user__username')
    list_filter = ('used',)
    readonly_fields = ('created_at', 'registered_at')


@admin.register(ChatThread)
class ChatThreadAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'title', 'messages_count', 'updated_at', 'created_date')
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

    def created_date(self, obj):
        try:
            return obj.created_at.date()
        except Exception:
            return None
    created_date.short_description = 'Created at'
    created_date.admin_order_field = 'created_at'


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
            membership, created = CohortMembership.objects.get_or_create(cohort=cohort, user=user, defaults={"role": "student"})
            if created:
                added.append(uname)
            else:
                existing.append(uname)

        # Defer messages to ModelAdmin.save_model where request is available
        self._bulk_add_result = {'added': added, 'existing': existing, 'missing': missing}
        return cohort


class CohortMembershipInline(admin.TabularInline):
    model = CohortMembership
    fk_name = 'cohort'
    extra = 0
    autocomplete_fields = ['user']
    fields = ('user', 'role', 'status', 'joined_at', 'added_by')
    readonly_fields = ('joined_at',)
    verbose_name = 'Member'
    verbose_name_plural = 'Members'


@admin.register(Cohort)
class CohortAdmin(admin.ModelAdmin):
    form = CohortAdminForm
    list_display = ('id', 'name', 'course', 'owner', 'code', 'created_at', 'updated_at')
    list_filter = ('course',)
    search_fields = ('name', 'code', 'description')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [CohortMembershipInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'course', 'code', 'description')
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
        # Ensure added_by is set to the current admin user for any memberships created without it
        CohortMembership.objects.filter(cohort=obj, added_by__isnull=True).update(added_by=request.user)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        # Handle deletions first
        for obj in getattr(formset, 'deleted_objects', []):
            try:
                obj.delete()
            except Exception:
                continue
        for obj in instances:
            if isinstance(obj, CohortMembership) and not getattr(obj, 'added_by_id', None):
                obj.added_by = request.user
            obj.save()
        formset.save_m2m()


@admin.register(QuizLog)
class QuizLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'module', 'cohort', 'teacher', 'student_count', 'completed_at')
    list_filter = ('cohort__course', 'cohort', 'module', 'teacher')
    search_fields = ('module__name', 'cohort__name', 'teacher__username')
    readonly_fields = ('completed_at',)
    ordering = ('-completed_at',)
    
    fieldsets = (
        (None, {
            'fields': ('cohort', 'module', 'teacher', 'student_count')
        }),
        ('Timestamps', {
            'fields': ('completed_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(TraceImage)
class TraceImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'trace', 'image_type', 'file_size_display', 'uploaded_at', 'created_at')
    list_filter = (('trace__user', admin.RelatedOnlyFieldListFilter), 'image_type', 'uploaded_at')
    search_fields = ('trace__user__username', 'upload_token')
    readonly_fields = ('image_preview', 'upload_token', 'uploaded_at', 'created_at', 'token_expires_at', 'file_size')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {
            'fields': ('trace', 'image_type', 'file_size', 'upload_token', 'token_expires_at')
        }),
        ('Image', {
            'fields': ('image_preview',)
        }),
        ('Timestamps', {
            'fields': ('uploaded_at', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def image_preview(self, obj):
        if not obj or not obj.image:
            return 'No image uploaded'
        try:
            data_url = f"data:{obj.image_type};base64,{obj.image}"
            return mark_safe(f'<img src="{data_url}" style="max-width: 800px; max-height: 600px;" />')
        except Exception as e:
            return f'Error displaying image: {str(e)}'
    image_preview.short_description = 'Image Preview'
    
    def file_size_display(self, obj):
        if not obj or not obj.file_size:
            return '0 bytes'
        size = obj.file_size
        if size < 1024:
            return f'{size} bytes'
        elif size < 1024 * 1024:
            return f'{size / 1024:.1f} KB'
        else:
            return f'{size / (1024 * 1024):.1f} MB'
    file_size_display.short_description = 'File Size'


@admin.register(MobileAuthToken)
class MobileAuthTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'token', 'used', 'expires_at', 'created_at')
    list_filter = (('user', admin.RelatedOnlyFieldListFilter), 'used', 'expires_at')
    search_fields = ('user__username', 'user__email', 'token')
    readonly_fields = ('token', 'created_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {
            'fields': ('user', 'token', 'used', 'expires_at')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
